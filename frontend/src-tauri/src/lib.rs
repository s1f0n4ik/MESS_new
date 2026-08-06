use std::collections::HashSet;
use std::sync::Mutex;

use tauri::{
    Manager, PhysicalPosition, PhysicalSize, RunEvent, WebviewUrl, WebviewWindowBuilder,
    WindowEvent,
};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

const PDF_W: u32 = 1968;
const PDF_H: u32 = 1392;
const PDF_OFFSET_X: i32 = 100;
const PDF_OFFSET_Y: i32 = -50;

/// Реестр живых окон: на X11 is_visible() отдаёт Ok(false) и для мёртвого
/// хэндла, отличить «свёрнуто» от «уничтожено» по нему нельзя.
struct LiveWindows(Mutex<HashSet<String>>);

/// Дочерний процесс бэкенда. Хранится, чтобы убить его при выходе:
/// иначе на Windows он остаётся висеть и держит порт 8787.
struct Backend(Mutex<Option<CommandChild>>);

/// Параметры запуска из командной строки.
#[derive(Clone, Debug)]
struct Launch {
    role: String,
    server: String,
    is_server: bool,
    fullscreen: bool,
    admin: bool,
}

fn parse_args() -> Launch {
    let args: Vec<String> = std::env::args().collect();
    let get = |key: &str| -> Option<String> {
        args.iter()
            .position(|a| a == key)
            .and_then(|i| args.get(i + 1))
            .cloned()
    };
    let role = get("--role").unwrap_or_else(|| "pc1".to_string());
    let server = get("--server").unwrap_or_else(|| "http://localhost:8787".to_string());
    Launch {
        is_server: args.iter().any(|a| a == "--serve"),
        fullscreen: !args.iter().any(|a| a == "--no-fullscreen"),
        admin: args.iter().any(|a| a == "--admin"),
        role,
        server,
    }
}

fn is_live(app: &tauri::AppHandle, label: &str) -> bool {
    app.state::<LiveWindows>()
        .0
        .lock()
        .map(|set| set.contains(label))
        .unwrap_or(false)
}

fn spawn_backend(app: &tauri::AppHandle) {
    let sidecar = match app.shell().sidecar("postcards-backend") {
        Ok(cmd) => cmd,
        Err(e) => {
            println!("[rs] sidecar not found: {e}");
            return;
        }
    };
    match sidecar.spawn() {
        Ok((mut rx, child)) => {
            println!("[rs] backend spawned pid={:?}", child.pid());
            if let Ok(mut slot) = app.state::<Backend>().0.lock() {
                *slot = Some(child);
            }
            // uvicorn пишет весь лог в stderr. Без этого канала падение
            // бэкенда выглядит как «окно открылось, но сцена не грузится».
            tauri::async_runtime::spawn(async move {
                while let Some(ev) = rx.recv().await {
                    match ev {
                        CommandEvent::Stderr(l) | CommandEvent::Stdout(l) => {
                            println!("[py] {}", String::from_utf8_lossy(&l).trim_end());
                        }
                        CommandEvent::Terminated(t) => {
                            println!("[rs] backend terminated: {:?}", t);
                        }
                        _ => {}
                    }
                }
            });
        }
        Err(e) => println!("[rs] backend spawn failed: {e}"),
    }
}

#[tauri::command]
fn minimize_all(app: tauri::AppHandle) {
    for (label, window) in app.webview_windows() {
        println!("[rs] minimize: {}", label);
        let _ = window.minimize();
    }
}

#[tauri::command]
fn main_fullscreen(app: tauri::AppHandle, on: bool) -> Result<(), String> {
    let main = app
        .get_webview_window("main")
        .ok_or_else(|| "main window not found".to_string())?;
    main.set_fullscreen(on).map_err(|e| e.to_string())
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
    let (pos_x, pos_y) = match main.current_monitor() {
        Ok(Some(mon)) => {
            let mp = *mon.position();
            let ms = *mon.size();
            let x = mp.x + (ms.width as i32 - PDF_W as i32) / 2 + PDF_OFFSET_X;
            let y = mp.y + (ms.height as i32 - PDF_H as i32) / 2 + PDF_OFFSET_Y;
            (x.max(mp.x), y.max(mp.y))
        }
        _ => {
            println!("[rs] WARN: no monitor info, fallback position");
            (0, 0)
        }
    };

    // WebviewUrl::App, а не External: Tauri сам подставит devUrl в разработке
    // и tauri://localhost в проде. С захардкоженным localhost:5173
    // упакованное приложение открыло бы чёрное окно.
    let url = WebviewUrl::App(format!("index.html?{}", query).into());

    let win = WebviewWindowBuilder::new(&app, &label, url)
        .title("PDF")
        .inner_size(PDF_W as f64 / scale, PDF_H as f64 / scale)
        .position(pos_x as f64 / scale, pos_y as f64 / scale)
        .decorations(false)
        .resizable(false)
        .visible(true)
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
            let _ = win_inner.set_size(PhysicalSize::new(PDF_W, PDF_H));
            let _ = win_inner.set_position(PhysicalPosition::new(pos_x, pos_y));
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

    let app = tauri::Builder::default()
        .manage(LiveWindows(Mutex::new(HashSet::new())))
        .manage(Backend(Mutex::new(None)))
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            minimize_all,
            main_fullscreen,
            open_pdf_window,
            close_pdf_window
        ])
        .setup(move |app| {
            let handle = app.handle().clone();

            if launch.is_server {
                spawn_backend(&handle);
            } else {
                println!("[rs] client mode, backend not started");
            }

            let query = format!(
                "role={}&server={}",
                urlencoding_lite(&launch.role),
                urlencoding_lite(&launch.server)
            );
            if launch.admin {
                query.push_str("&admin=1");
            let win = WebviewWindowBuilder::new(
                &handle,
                "main",
                WebviewUrl::App(format!("index.html?{}", query).into()),
            )
            .title("Postcards")
            .inner_size(1600.0, 900.0)
            .fullscreen(launch.fullscreen)
            .build()?;
            let _ = win.set_focus();

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|handle, event| {
        // Без явного kill бэкенд остаётся жить после закрытия окна
        // и держит порт 8787 — следующий запуск падает на bind.
        if let RunEvent::ExitRequested { .. } | RunEvent::Exit = event {
            if let Ok(mut slot) = handle.state::<Backend>().0.lock() {
                if let Some(child) = slot.take() {
                    println!("[rs] killing backend");
                    let _ = child.kill();
                }
            }
        }
    });
}

/// Минимальное экранирование для query: тащить зависимость ради двух
/// подстановок смысла нет, а роль и адрес — контролируемые значения.
fn urlencoding_lite(s: &str) -> String {
    s.replace('&', "%26").replace(' ', "%20").replace('#', "%23")
}