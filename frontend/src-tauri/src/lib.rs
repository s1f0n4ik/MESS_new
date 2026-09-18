mod backend;

use std::collections::HashSet;
use std::path::PathBuf;
use std::sync::Mutex;

use serde::{Deserialize, Serialize};
use tauri::{
    Manager, PhysicalPosition, PhysicalSize, RunEvent, WebviewUrl, WebviewWindowBuilder,
    WindowEvent,
};

// ---------- Геометрия PDF-окна ----------
// Эталон — монитор выставки 34" 3440x1440 (сетка сцены та же). На нём окно
// 1968x1392 со смещением (+100, -50) от центра. На других экранах всё
// масштабируется единым коэффициентом по меньшей оси: пропорции окна
// сохраняются, на эталоне k = 1 и геометрия ровно прежняя.
const REF_MON_W: f64 = 3440.0;
const REF_MON_H: f64 = 1440.0;
const PDF_W: f64 = 1968.0;
const PDF_H: f64 = 1392.0;
const PDF_OFFSET_X: f64 = 100.0;
const PDF_OFFSET_Y: f64 = -50.0;

/// Реестр живых окон: на X11 is_visible() отдаёт Ok(false) и для мёртвого
/// хэндла, отличить «свёрнуто» от «уничтожено» по нему нельзя.
struct LiveWindows(Mutex<HashSet<String>>);

/// PDF-окна, свёрнутые пользователем (Esc в окне, кнопка, клавиша P).
/// Пока метка стоит, open_pdf_window по живому окну ничего не делает —
/// иначе любой повторный open по смене токена разворачивал бы окно обратно.
struct UserMinimized(Mutex<HashSet<String>>);

fn set_user_minimized(app: &tauri::AppHandle, label: &str, on: bool) {
    if let Ok(mut set) = app.state::<UserMinimized>().0.lock() {
        if on {
            set.insert(label.to_string());
        } else {
            set.remove(label);
        }
    }
}

fn is_user_minimized(app: &tauri::AppHandle, label: &str) -> bool {
    app.state::<UserMinimized>()
        .0
        .lock()
        .map(|s| s.contains(label))
        .unwrap_or(false)
}

/// Все окна, кроме главного — это PDF-окна этой машины.
fn pdf_labels(app: &tauri::AppHandle) -> Vec<String> {
    app.webview_windows()
        .keys()
        .filter(|l| l.as_str() != "main")
        .cloned()
        .collect()
}

// ---------- launch.json: роль машины без командной строки ----------

#[derive(Serialize, Deserialize, Clone, Debug)]
#[serde(default)]
struct LaunchFile {
    role: String,
    server: String,
    serve: bool,
    admin: bool,
    fullscreen: bool,
}

impl Default for LaunchFile {
    fn default() -> Self {
        Self {
            role: "pc1".into(),
            server: "http://localhost:8787".into(),
            serve: true,
            admin: true,
            fullscreen: true,
        }
    }
}

/// Та же папка, что использует бэкенд (paths.py): POSTCARDS_BASE_DIR,
/// иначе %LOCALAPPDATA%\Postcards на Windows, ~/.config/postcards на Linux.
/// Передаётся бэкенду явно через env, чтобы обе стороны смотрели в одно место.
fn data_root() -> PathBuf {
    if let Ok(p) = std::env::var("POSTCARDS_BASE_DIR") {
        return PathBuf::from(p);
    }
    #[cfg(target_os = "windows")]
    {
        if let Ok(p) = std::env::var("LOCALAPPDATA") {
            return PathBuf::from(p).join("Postcards");
        }
    }
    if let Ok(h) = std::env::var("HOME") {
        return PathBuf::from(h).join(".config").join("postcards");
    }
    std::env::temp_dir().join("postcards")
}

fn launch_file_path() -> PathBuf {
    data_root().join("launch.json")
}

fn read_launch_file() -> Option<LaunchFile> {
    let text = std::fs::read_to_string(launch_file_path()).ok()?;
    match serde_json::from_str::<LaunchFile>(&text) {
        Ok(cfg) => Some(cfg),
        Err(e) => {
            println!("[rs] launch.json unreadable: {e}");
            None
        }
    }
}

fn write_launch_file(cfg: &LaunchFile) -> Result<(), String> {
    let path = launch_file_path();
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir).map_err(|e| e.to_string())?;
    }
    let text = serde_json::to_string_pretty(cfg).map_err(|e| e.to_string())?;
    std::fs::write(&path, text).map_err(|e| e.to_string())?;
    println!("[rs] launch.json written: {}", path.display());
    Ok(())
}

/// Параметры запуска: аргументы CLI > launch.json > дефолты.
#[derive(Clone, Debug)]
struct Launch {
    role: String,
    server: String,
    is_server: bool,
    fullscreen: bool,
    admin: bool,
    needs_setup: bool,
}

fn parse_args() -> Launch {
    let args: Vec<String> = std::env::args().collect();
    let has = |k: &str| args.iter().any(|a| a == k);
    let get = |key: &str| -> Option<String> {
        args.iter()
            .position(|a| a == key)
            .and_then(|i| args.get(i + 1))
            .cloned()
    };

    let file = read_launch_file();
    let from_args = get("--role").is_some() || get("--server").is_some() || has("--serve");
    // Экран настройки: явно по --setup, либо когда нет ни файла, ни аргументов —
    // это первый запуск после установки.
    let needs_setup = has("--setup") || (file.is_none() && !from_args);
    let f = file.as_ref();

    Launch {
        role: get("--role")
            .or_else(|| f.map(|c| c.role.clone()))
            .unwrap_or_else(|| "pc1".to_string()),
        server: get("--server")
            .or_else(|| f.map(|c| c.server.clone()))
            .unwrap_or_else(|| "http://localhost:8787".to_string()),
        is_server: has("--serve") || f.map(|c| c.serve).unwrap_or(false),
        admin: has("--admin") || f.map(|c| c.admin).unwrap_or(false),
        fullscreen: !has("--no-fullscreen") && f.map(|c| c.fullscreen).unwrap_or(true),
        needs_setup,
    }
}

fn is_live(app: &tauri::AppHandle, label: &str) -> bool {
    app.state::<LiveWindows>()
        .0
        .lock()
        .map(|set| set.contains(label))
        .unwrap_or(false)
}

/// Старт бэкенда через собственный лаунчер (backend.rs): вывод уходит в файл,
/// а не в пайп shell-плагина — забитый пайп подвешивал Python-процесс,
/// и приложение видело «бэкенд есть, но не отвечает».
fn start_backend() {
    let base = data_root();
    match backend::start(&base) {
        Ok(()) => println!(
            "[rs] backend launched, log: {}",
            base.join("backend.log").display()
        ),
        Err(e) => println!("[rs] backend start failed: {e}"),
    }
}

// ---------- Команды launch-конфига ----------

#[tauri::command]
fn get_launch_config() -> Option<LaunchFile> {
    read_launch_file()
}

#[tauri::command]
fn save_launch_config(config: LaunchFile) -> Result<(), String> {
    println!("[rs] launch config saved: {:?}", config);
    write_launch_file(&config)
}

/// «Сменить роль» из админки: стираем файл и перезапускаемся — приложение
/// снова покажет экран выбора.
#[tauri::command]
fn reset_launch_config(app: tauri::AppHandle) {
    let _ = std::fs::remove_file(launch_file_path());
    backend::stop();
    std::thread::sleep(std::time::Duration::from_millis(300));
    app.restart();
}

#[tauri::command]
fn restart_app(app: tauri::AppHandle) {
    backend::stop();
    // Даём порту 8787 освободиться, иначе новый бэкенд упадёт на bind.
    std::thread::sleep(std::time::Duration::from_millis(300));
    app.restart();
}

// ---------- Окна ----------

#[tauri::command]
fn minimize_all(app: tauri::AppHandle) {
    for (label, window) in app.webview_windows() {
        println!("[rs] minimize: {}", label);
        let _ = window.minimize();
    }
}

/// Вызывается из самого PDF-окна (Esc / кнопка): Tauri подставляет окно-вызывающего.
#[tauri::command]
fn minimize_this_window(app: tauri::AppHandle, window: tauri::WebviewWindow) -> Result<(), String> {
    let label = window.label().to_string();
    println!("[rs] minimize by user: {}", label);
    if label != "main" {
        set_user_minimized(&app, &label, true);
    }
    window.minimize().map_err(|e| e.to_string())
}

#[tauri::command]
fn minimize_pdf_windows(app: tauri::AppHandle) -> usize {
    let mut n = 0;
    for label in pdf_labels(&app) {
        if let Some(w) = app.get_webview_window(&label) {
            set_user_minimized(&app, &label, true);
            if w.minimize().is_ok() {
                n += 1;
            }
        }
    }
    println!("[rs] minimize_pdf_windows: {}", n);
    n
}

#[tauri::command]
fn restore_pdf_windows(app: tauri::AppHandle) -> usize {
    let mut n = 0;
    for label in pdf_labels(&app) {
        if let Some(w) = app.get_webview_window(&label) {
            set_user_minimized(&app, &label, false);
            let _ = w.unminimize();
            let _ = w.show();
            let _ = w.set_focus();
            n += 1;
        }
    }
    println!("[rs] restore_pdf_windows: {}", n);
    n
}

/// Клавиша P в главном окне. true — окна развернули, false — свернули/нет окон.
#[tauri::command]
fn toggle_pdf_windows(app: tauri::AppHandle) -> bool {
    let labels = pdf_labels(&app);
    if labels.is_empty() {
        return false;
    }
    let any_minimized = labels.iter().any(|l| {
        app.get_webview_window(l)
            .and_then(|w| w.is_minimized().ok())
            .unwrap_or(false)
    });
    if any_minimized {
        restore_pdf_windows(app);
        true
    } else {
        minimize_pdf_windows(app);
        false
    }
}

#[tauri::command]
fn main_fullscreen(app: tauri::AppHandle, on: bool) -> Result<(), String> {
    let main = app
        .get_webview_window("main")
        .ok_or_else(|| "main window not found".to_string())?;
    main.set_fullscreen(on).map_err(|e| e.to_string())
}

#[derive(Clone, Copy, Debug)]
struct PdfGeometry {
    w: u32,
    h: u32,
    x: i32,
    y: i32,
}

fn pdf_geometry(main: &tauri::WebviewWindow) -> PdfGeometry {
    let (mp, ms) = match main.current_monitor() {
        Ok(Some(mon)) => (*mon.position(), *mon.size()),
        _ => {
            println!("[rs] WARN: no monitor info, assuming reference monitor");
            (
                PhysicalPosition::new(0, 0),
                PhysicalSize::new(REF_MON_W as u32, REF_MON_H as u32),
            )
        }
    };
    let (mw, mh) = (ms.width as f64, ms.height as f64);
    let k = (mw / REF_MON_W).min(mh / REF_MON_H);

    let w = ((PDF_W * k).round() as u32).min(ms.width).max(320);
    let h = ((PDF_H * k).round() as u32).min(ms.height).max(240);

    let x = mp.x + ((mw - w as f64) / 2.0 + PDF_OFFSET_X * k).round() as i32;
    let y = mp.y + ((mh - h as f64) / 2.0 + PDF_OFFSET_Y * k).round() as i32;

    // Не выпускаем окно за края монитора.
    let max_x = mp.x + ms.width.saturating_sub(w) as i32;
    let max_y = mp.y + ms.height.saturating_sub(h) as i32;
    let x = x.clamp(mp.x, max_x.max(mp.x));
    let y = y.clamp(mp.y, max_y.max(mp.y));

    println!(
        "[rs] pdf geometry: monitor {}x{} k={:.3} -> {}x{} at ({}, {})",
        ms.width, ms.height, k, w, h, x, y
    );
    PdfGeometry { w, h, x, y }
}

#[tauri::command]
async fn open_pdf_window(
    app: tauri::AppHandle,
    label: String,
    query: String,
) -> Result<(), String> {
    println!("[rs] open_pdf_window: label={} query={}", label, query);

    if is_live(&app, &label) {
        if let Some(existing) = app.get_webview_window(&label) {
            if is_user_minimized(&app, &label) {
                println!("[rs] window alive, minimized by user -> leave it");
                return Ok(());
            }
            println!("[rs] window alive -> unminimize + focus");
            let _ = existing.unminimize();
            let _ = existing.show();
            let _ = existing.set_focus();
            return Ok(());
        }
    }

    if let Some(stale) = app.get_webview_window(&label) {
        println!("[rs] stale handle -> destroy before recreate");
        let _ = stale.destroy();
        tokio::time::sleep(std::time::Duration::from_millis(120)).await;
    }

    let main = app
        .get_webview_window("main")
        .ok_or_else(|| "no main window".to_string())?;

    let scale = main.scale_factor().unwrap_or(1.0);
    let g = pdf_geometry(&main);

    // WebviewUrl::App, а не External: Tauri сам подставит devUrl в разработке
    // и tauri://localhost в проде.
    let url = WebviewUrl::App(format!("index.html?{}", query).into());

    let win = WebviewWindowBuilder::new(&app, &label, url)
        .title("PDF")
        .inner_size(g.w as f64 / scale, g.h as f64 / scale)
        .position(g.x as f64 / scale, g.y as f64 / scale)
        .decorations(false)
        .resizable(false)
        .visible(true)
        .zoom_hotkeys_enabled(false)
        .build()
        .map_err(|e| {
            println!("[rs] ERR build: {e}");
            e.to_string()
        })?;

    if let Ok(mut set) = app.state::<LiveWindows>().0.lock() {
        set.insert(label.clone());
    }

    {
        let app_ev = app.clone();
        let label_ev = label.clone();
        win.on_window_event(move |event| {
            if let WindowEvent::Destroyed = event {
                if let Ok(mut set) = app_ev.state::<LiveWindows>().0.lock() {
                    set.remove(&label_ev);
                }
                // Метка «свёрнуто пользователем» живёт не дольше окна:
                // следующее открытие сценарием должно показать окно.
                set_user_minimized(&app_ev, &label_ev, false);
                println!("[rs] window destroyed: {}", label_ev);
            }
        });
    }

    let app_geo = app.clone();
    let label_geo = label.clone();
    let win_outer = win.clone();
    let win_inner = win.clone();
    tauri::async_runtime::spawn(async move {
        tokio::time::sleep(std::time::Duration::from_millis(250)).await;
        if !is_live(&app_geo, &label_geo) {
            println!("[rs] geometry skipped: window gone ({})", label_geo);
            return;
        }
        let _ = win_outer.run_on_main_thread(move || {
            let _ = win_inner.set_size(PhysicalSize::new(g.w, g.h));
            let _ = win_inner.set_position(PhysicalPosition::new(g.x, g.y));
            let _ = win_inner.set_focus();
            println!("[rs] geometry applied");
        });
    });

    println!("[rs] done");
    Ok(())
}

#[tauri::command]
async fn close_pdf_window(app: tauri::AppHandle, label: String) -> Result<(), String> {
    println!("[rs] close_pdf_window: {}", label);
    if let Some(win) = app.get_webview_window(&label) {
        win.destroy().map_err(|e| e.to_string())?;
    }
    if let Ok(mut set) = app.state::<LiveWindows>().0.lock() {
        set.remove(&label);
    }
    set_user_minimized(&app, &label, false);
    Ok(())
}

#[cfg(target_os = "linux")]
fn init_x11_threads() {
    unsafe {
        if x11::xlib::XInitThreads() == 0 {
            println!("[rs] WARN: XInitThreads failed");
        } else {
            println!("[rs] XInitThreads OK");
        }
    }
}

#[cfg(not(target_os = "linux"))]
fn init_x11_threads() {}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    init_x11_threads();

    let launch = parse_args();
    println!("[rs] launch: {:?}", launch);
    println!("[rs] launch.json path: {}", launch_file_path().display());

    let app = tauri::Builder::default()
        .manage(LiveWindows(Mutex::new(HashSet::new())))
        .manage(UserMinimized(Mutex::new(HashSet::new())))
        // shell-плагин больше не запускает бэкенд, но на него ссылается
        // capability shell:allow-execute — оставляем, пока не вычистим её.
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            minimize_all,
            main_fullscreen,
            open_pdf_window,
            close_pdf_window,
            get_launch_config,
            save_launch_config,
            reset_launch_config,
            restart_app,
            minimize_this_window,
            minimize_pdf_windows,
            restore_pdf_windows,
            toggle_pdf_windows
        ])
        .setup(move |app| {
            let handle = app.handle().clone();

            if launch.needs_setup {
                // Первый запуск: экран выбора роли, бэкенд не стартуем.
                println!("[rs] setup mode");
                let win = WebviewWindowBuilder::new(
                    &handle,
                    "main",
                    WebviewUrl::App("index.html?setup=1".into()),
                )
                .title("Postcards — настройка")
                .inner_size(900.0, 700.0)
                .center()
                .zoom_hotkeys_enabled(false)
                .build()?;
                let _ = win.set_focus();
                return Ok(());
            }

            if launch.is_server {
                start_backend();
            } else {
                println!("[rs] client mode, backend not started");
            }

            let mut query = format!(
                "role={}&server={}",
                urlencoding_lite(&launch.role),
                urlencoding_lite(&launch.server)
            );
            if launch.admin {
                query.push_str("&admin=1");
            }
            println!("[rs] main window query = {}", query);

            let win = WebviewWindowBuilder::new(
                &handle,
                "main",
                WebviewUrl::App(format!("index.html?{}", query).into()),
            )
            .title("Heritage")
            .inner_size(1600.0, 900.0)
            .fullscreen(launch.fullscreen)
            .zoom_hotkeys_enabled(false)
            .build()?;
            let _ = win.set_focus();

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|_handle, event| {
        // Без явного kill бэкенд остаётся жить после закрытия окна
        // и держит порт 8787 — следующий запуск падает на bind.
        if let RunEvent::ExitRequested { .. } | RunEvent::Exit = event {
            backend::stop();
        }
    });
}

/// Минимальное экранирование для query: тащить зависимость ради двух
/// подстановок смысла нет, а роль и адрес — контролируемые значения.
fn urlencoding_lite(s: &str) -> String {
    s.replace('&', "%26").replace(' ', "%20").replace('#', "%23")
}