use tauri::{
    Manager, PhysicalPosition, PhysicalSize, WebviewUrl, WebviewWindowBuilder,
};

// Геометрия из ТЗ (физические пиксели).
const PDF_W: u32 = 1968;
const PDF_H: u32 = 1392;
// Смещение от центра: вправо 100, вверх 50.
const PDF_OFFSET_X: i32 = 100;
const PDF_OFFSET_Y: i32 = -50;

#[tauri::command]
fn minimize_all(app: tauri::AppHandle) {
    for (_label, window) in app.webview_windows() {
        let _ = window.minimize();
    }
}

/// Создаёт (или переиспользует) PDF-окно на том же мониторе, где главное окно.
#[tauri::command]
async fn open_pdf_window(
    app: tauri::AppHandle,
    label: String,
    query: String,
) -> Result<(), String> {
    eprintln!("[rs] open_pdf_window: label={} query={}", label, query);

    if let Some(existing) = app.get_webview_window(&label) {
        eprintln!("[rs] window already exists -> focus");
        let _ = existing.show();
        let _ = existing.set_focus();
        return Ok(());
    }

    let main = app.get_webview_window("main")
        .ok_or_else(|| { eprintln!("[rs] ERR: no main window"); "no main window".to_string() })?;

    let mut target = main.url().map_err(|e| { eprintln!("[rs] ERR url: {e}"); e.to_string() })?;
    target.set_path("/");
    target.set_query(Some(&query));
    target.set_fragment(None);
    eprintln!("[rs] target url = {}", target);

    let win = WebviewWindowBuilder::new(&app, &label, WebviewUrl::External(target))
        .title("PDF")
        .inner_size(PDF_W as f64, PDF_H as f64)
        .decorations(false)
        .resizable(false)
        .build()
        .map_err(|e| { eprintln!("[rs] ERR build: {e}"); e.to_string() })?;

    eprintln!("[rs] window built OK");

    let _ = win.set_size(PhysicalSize::new(PDF_W, PDF_H));
    let _ = win.set_position(PhysicalPosition::new(PDF_OFFSET_X, PDF_OFFSET_Y));
    let _ = win.set_focus();

    eprintln!("[rs] done");
    Ok(())
}

#[tauri::command]
async fn close_pdf_window(app: tauri::AppHandle, label: String) -> Result<(), String> {
    if let Some(win) = app.get_webview_window(&label) {
        win.destroy().map_err(|e| e.to_string())?;
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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
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
