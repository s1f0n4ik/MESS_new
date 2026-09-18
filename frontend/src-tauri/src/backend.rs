//! Лаунчер бэкенда: запуск postcards-backend рядом с exe приложения,
//! вывод в файл backend.log, добивание орфана с прошлого запуска.
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

/// `base_dir` — та же папка, где лежит launch.json (data_root() в lib.rs).
/// Передаётся бэкенду через POSTCARDS_BASE_DIR, чтобы data/ и лог оказались
/// в одном месте независимо от того, откуда запущен exe (target\debug или
/// Program Files).
pub fn start(base_dir: &Path) -> Result<(), String> {
    let exe_dir: PathBuf = std::env::current_exe()
        .map_err(|e| e.to_string())?
        .parent()
        .ok_or("no exe dir")?
        .to_path_buf();
    // tauri-build копирует externalBin рядом с exe уже без суффикса triple —
    // и в dev (target\debug), и в установленном приложении.
    let backend = exe_dir.join(BACKEND_FILE);
    if !backend.exists() {
        return Err(format!("нет файла {}", backend.display()));
    }

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

    let mut cmd = Command::new(&backend);
    cmd.current_dir(&exe_dir)
        .stdin(Stdio::null())
        .stdout(Stdio::from(log))
        .stderr(Stdio::from(err))
        .env("POSTCARDS_BASE_DIR", base_dir)
        .env("POSTCARDS_PORT", PORT.to_string())
        // Без консоли Python пишет в cp1251 и падает на «→»/эмодзи в логах.
        .env("PYTHONUTF8", "1")
        .env("PYTHONIOENCODING", "utf-8")
        .env("PYTHONUNBUFFERED", "1");
    hidden(&mut cmd);

    let child = cmd.spawn().map_err(|e| e.to_string())?;
    *CHILD.lock().unwrap() = Some(child);

    // Ждём порт до 20 с и пишем результат в тот же лог.
    std::thread::spawn(move || {
        let t0 = Instant::now();
        while t0.elapsed() < Duration::from_secs(20) {
            if port_open() {
                append_log(&log_path, &format!("[launcher] backend up in {:?}", t0.elapsed()));
                return;
            }
            std::thread::sleep(Duration::from_millis(250));
        }
        append_log(&log_path, "[launcher] backend NOT up after 20s");
    });
    Ok(())
}

pub fn stop() {
    if let Some(mut c) = CHILD.lock().unwrap().take() {
        let _ = c.kill();
        let _ = c.wait();
    }
    kill_stale();
}