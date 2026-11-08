//! Лаунчер бэкенда: актуальный postcards-backend встроен в приложение и
//! извлекается в data_root/runtime. Так UI и backend всегда одной сборки.
//! Не используем tauri-plugin-shell: его пайп ёмкостью 1 событие при
//! нечитаемом rx забивался и подвешивал Python на первом же print().

use std::{
    fs::OpenOptions,
    io::Write,
    net::{SocketAddr, TcpStream},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::Mutex,
    time::{Duration, Instant},
};

#[cfg(windows)]
use std::os::windows::process::CommandExt;
#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

const PORT: u16 = 8787;

#[cfg(windows)]
const BACKEND_FILE: &str = "postcards-backend.exe";
#[cfg(not(windows))]
const BACKEND_FILE: &str = "postcards-backend";

static CHILD: Mutex<Option<Child>> = Mutex::new(None);

fn hidden(cmd: &mut Command) -> &mut Command {
    #[cfg(windows)]
    cmd.creation_flags(CREATE_NO_WINDOW);
    cmd
}

fn port_open() -> bool {
    TcpStream::connect_timeout(
        &SocketAddr::from(([127, 0, 0, 1], PORT)),
        Duration::from_millis(300),
    )
    .is_ok()
}

// Орфан с прошлого запуска либо держит порт, либо висит на забитом пайпе —
// в обоих случаях новый экземпляр не поднимется. Убиваем по имени.
fn kill_stale() {
    #[cfg(windows)]
    let _ = hidden(&mut Command::new("taskkill"))
        .args(["/F", "/T", "/IM", BACKEND_FILE])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();
    #[cfg(not(windows))]
    let _ = Command::new("pkill")
        .args(["-f", BACKEND_FILE])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();
}

fn append_log(path: &Path, line: &str) {
    if let Ok(mut f) = OpenOptions::new().create(true).append(true).open(path) {
        let _ = writeln!(f, "{line}");
    }
}

fn bundled_backend() -> Result<PathBuf, String> {
    let exe_dir = std::env::current_exe()
        .map_err(|e| e.to_string())?
        .parent()
        .ok_or("no exe dir")?
        .to_path_buf();
    let backend = exe_dir.join(BACKEND_FILE);
    if !backend.is_file() {
        return Err(format!("серверный компонент не найден: {}", backend.display()));
    }
    Ok(backend)
}

/// `base_dir` — та же папка, где лежит launch.json (data_root() в lib.rs).
/// Передаётся бэкенду через POSTCARDS_BASE_DIR, чтобы data/ и лог оказались
/// в одном месте независимо от того, откуда запущен exe (target\debug или
/// Program Files).
pub fn start(base_dir: &Path, resource_dir: &Path) -> Result<(), String> {
    let exe_dir: PathBuf = std::env::current_exe()
        .map_err(|e| e.to_string())?
        .parent()
        .ok_or("no exe dir")?
        .to_path_buf();
    std::fs::create_dir_all(base_dir).map_err(|e| e.to_string())?;
    let log_path = base_dir.join("backend.log");
    let log = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_path)
        .map_err(|e| e.to_string())?;
    append_log(
        &log_path,
        &format!("\n==== launch {:?} ====", std::time::SystemTime::now()),
    );
    let err = log.try_clone().map_err(|e| e.to_string())?;

    kill_stale();
    if port_open() {
        std::thread::sleep(Duration::from_millis(700));
    }
    let backend = bundled_backend()?;
    let pdf_template = resource_dir
        .join("pdfs-default")
        .join("Postcards_2x2_template_14_blocks.pdf");
    if !pdf_template.is_file() {
        return Err(format!("PDF-шаблон не найден: {}", pdf_template.display()));
    }
    append_log(
        &log_path,
        &format!(
            "[launcher] bundled backend: {} ({} bytes)",
            backend.display(),
            std::fs::metadata(&backend).map(|m| m.len()).unwrap_or(0)
        ),
    );

    let mut cmd = Command::new(&backend);
    cmd.current_dir(backend.parent().unwrap_or(&exe_dir))
        .stdin(Stdio::null())
        .stdout(Stdio::from(log))
        .stderr(Stdio::from(err))
        .env("POSTCARDS_BASE_DIR", base_dir)
        .env("POSTCARDS_PORT", PORT.to_string())
        .env("POSTCARDS_PDF_TEMPLATE", &pdf_template)
        // Без консоли Python пишет в cp1251 и падает на «→»/эмодзи в логах.
        .env("PYTHONUTF8", "1")
        .env("PYTHONIOENCODING", "utf-8")
        .env("PYTHONUNBUFFERED", "1");
    hidden(&mut cmd);

    let mut child = cmd.spawn().map_err(|e| e.to_string())?;

    // Не открываем рабочий экран, пока координатор действительно не готов.
    // Раньше UI появлялся сразу и показывал только вечное «WS: offline».
    let t0 = Instant::now();
    while t0.elapsed() < Duration::from_secs(30) {
        if port_open() {
            append_log(&log_path, &format!("[launcher] backend up in {:?}", t0.elapsed()));
            *CHILD.lock().unwrap() = Some(child);
            return Ok(());
        }
        if let Some(status) = child.try_wait().map_err(|e| e.to_string())? {
            let message = format!("сервер завершился при запуске: {status}");
            append_log(&log_path, &format!("[launcher] {message}"));
            return Err(message);
        }
        std::thread::sleep(Duration::from_millis(250));
    }
    let _ = child.kill();
    let _ = child.wait();
    append_log(&log_path, "[launcher] backend NOT up after 30s");
    Err("координатор не запустился за 30 секунд; подробности в backend.log".into())
}

pub fn stop() {
    if let Some(mut c) = CHILD.lock().unwrap().take() {
        let _ = c.kill();
        let _ = c.wait();
    }
    kill_stale();
}
