use std::collections::HashSet;
use std::sync::Mutex;

use tauri::{
    Manager, PhysicalPosition, PhysicalSize, WebviewUrl, WebviewWindowBuilder, WindowEvent,
};

// Геометрия из ТЗ (физические пиксели).
const PDF_W: u32 = 1968;
const PDF_H: u32 = 1392;
// Смещение от центра: вправо 100, вверх 50.
const PDF_OFFSET_X: i32 = 100;
const PDF_OFFSET_Y: i32 = -50;

/// Реестр реально живых окон. Нужен потому, что на X11 `is_visible()`
/// возвращает Ok(false) и для окна с уже мёртвым нативным хэндлом —
/// то есть отличить «свёрнуто» от «уничтожено» по нему нельзя.
struct LiveWindows(Mutex<HashSet<String>>);

fn is_live(app: &tauri::AppHandle, label: &str) -> bool {
    app.state::<LiveWindows>()
        .0
        .lock()
        .map(|set| set.contains(label))
        .unwrap_or(false)
}

#[tauri::command]
fn minimize_all(app: tauri::AppHandle) {
    for (label, window) in app.webview_windows() {
        eprintln!("[rs] minimize: {}", label);
        let _ = window.minimize();
    }
}

#[tauri::command]
async fn open_pdf_window(
    app: tauri::AppHandle,
    label: String,
    query: String,
) -> Result<(), String> {
    eprintln!("[rs] open_pdf_window: label={} query={}", label, query);

    // 1. Окно уже есть и живое -> просто поднять.
    if is_live(&app, &label) {
        if let Some(existing) = app.get_webview_window(&label) {
            eprintln!("[rs] window alive -> unminimize + focus");
            let _ = existing.unminimize();
            let _ = existing.show();
            let _ = existing.set_focus();
            return Ok(());
        }
    }

    // 2. Реестр не знает про окно, но Tauri держит осиротевший хэндл -> снести.
    if let Some(stale) = app.get_webview_window(&label) {
        eprintln!("[rs] stale handle -> destroy before recreate");
        let _ = stale.destroy();
        tokio::time::sleep(std::time::Duration::from_millis(120)).await;
    }

    let main = app
        .get_webview_window("main")
        .ok_or_else(|| "no main window".to_string())?;

    let mut target = main.url().map_err(|e| e.to_string())?;
    target.set_path("/");
    target.set_query(Some(&query));
    target.set_fragment(None);
    eprintln!("[rs] target url = {}", target);

    // Геометрию считаем ДО build(): никаких X-запросов к ещё не смапленному окну.
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
            eprintln!("[rs] WARN: no monitor info, using fallback position");
            (0, 0)
        }
    };
    eprintln!(
        "[rs] planned position -> ({}, {}), scale={}",
        pos_x, pos_y, scale
    );

    // inner_size/position в билдере — логические единицы, поэтому делим на scale.
    let win = WebviewWindowBuilder::new(&app, &label, WebviewUrl::External(target))
        .title("PDF")
        .inner_size(PDF_W as f64 / scale, PDF_H as f64 / scale)
        .position(pos_x as f64 / scale, pos_y as f64 / scale)
        .decorations(false)
        .resizable(false)
        .visible(true)
        .build()
        .map_err(|e| {
            eprintln!("[rs] ERR build: {e}");
            e.to_string()
        })?;

    // Регистрируем как живое и подписываемся на уничтожение.
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
                eprintln!("[rs] window destroyed: {}", label_ev);
            }
        });
    }

    eprintln!("[rs] window built OK");

    // Точную физическую геометрию выставляем отложенно и строго из GTK-потока:
    // прямой вызов из async-воркера — это гонка с WebKit по X-соединению.
    let app_geo = app.clone();
    let label_geo = label.clone();
    let win_outer = win.clone();
    let win_inner = win.clone();
    tauri::async_runtime::spawn(async move {
        tokio::time::sleep(std::time::Duration::from_millis(250)).await;
        if !is_live(&app_geo, &label_geo) {
            eprintln!("[rs] geometry skipped: window gone ({})", label_geo);
            return;
        }
        let _ = win_outer.run_on_main_thread(move || {
            let _ = win_inner.set_size(PhysicalSize::new(PDF_W, PDF_H));
            let _ = win_inner.set_position(PhysicalPosition::new(pos_x, pos_y));
            let _ = win_inner.set_focus();
            eprintln!("[rs] geometry applied");
        });
    });

    eprintln!("[rs] done");
    Ok(())
}

#[tauri::command]
async fn close_pdf_window(app: tauri::AppHandle, label: String) -> Result<(), String> {
    eprintln!("[rs] close_pdf_window: {}", label);
    if let Some(win) = app.get_webview_window(&label) {
        win.destroy().map_err(|e| e.to_string())?;
    }
    if let Ok(mut set) = app.state::<LiveWindows>().0.lock() {
        set.remove(&label);
    }
    Ok(())
}

/// Разворачивает главное окно на весь текущий монитор (для боевого стенда).
#[tauri::command]
fn main_fullscreen(app: tauri::AppHandle, on: bool) -> Result<(), String> {
    let main = app
        .get_webview_window("main")
        .ok_or_else(|| "main window not found".to_string())?;
    main.set_fullscreen(on).map_err(|e| e.to_string())
}

#[cfg(target_os = "linux")]
fn init_x11_threads() {
    unsafe {
        // Обязательно до gtk_init. Возвращает 0 при неудаче.
        if x11::xlib::XInitThreads() == 0 {
            eprintln!("[rs] WARN: XInitThreads failed");
        } else {
            eprintln!("[rs] XInitThreads OK");
        }
    }
}

#[cfg(not(target_os = "linux"))]
fn init_x11_threads() {}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    init_x11_threads();

    tauri::Builder::default()
        .manage(LiveWindows(Mutex::new(HashSet::new())))
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            minimize_all,
            open_pdf_window,
            close_pdf_window,
            main_fullscreen
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}