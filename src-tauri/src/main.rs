// 在 release 模式下不显示控制台窗口
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::process::Command;
use tauri::{Emitter, Manager};
use tauri::menu::{Menu, MenuItem};
use tauri_plugin_global_shortcut::GlobalShortcutExt;
use tauri_plugin_log::{Target, TargetKind};

// Windows: 调用子进程时不显示 cmd 窗口
#[cfg(windows)]
use std::os::windows::process::CommandExt;
#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x08000000;

#[derive(Debug, Serialize, Deserialize)]
struct OcrResult {
    success: bool,
    text: String,
    error: Option<String>,
    /// 截图文件路径（用于前端预览）
    png_path: Option<String>,
    /// 后端解析的结构化字段 {subject, subject_id, question_type, content, answer}
    parsed: Option<serde_json::Value>,
    /// Rust 端是否已自动保存到错题本
    saved: bool,
    /// 保存失败原因
    save_error: Option<String>,
    /// 保存后的错题 ID
    saved_id: Option<i64>,
}

/// 查找 grab_window.py 脚本路径
/// 查找顺序：
/// 1. Tauri 资源目录下的 grab_window.py（生产环境打包后）
/// 2. 可执行文件同目录下的 tools/grab_window.py（便携部署）
/// 3. 可执行文件上三级目录的 tools/grab_window.py（开发环境，exe 在 src-tauri/target/release/）
/// 4. 当前工作目录的 tools/grab_window.py
fn find_grab_script(app_handle: &tauri::AppHandle) -> Option<PathBuf> {
    let mut candidates: Vec<PathBuf> = Vec::new();

    // 1. Tauri 资源目录（含 _up_ 子目录变体，NSIS 安装时资源可能在此）
    if let Ok(resource_dir) = app_handle.path().resource_dir() {
        candidates.push(resource_dir.join("grab_window.py"));
        candidates.push(resource_dir.join("tools").join("grab_window.py"));
        candidates.push(resource_dir.join("_up_").join("tools").join("grab_window.py"));
        candidates.push(resource_dir.join("_up_").join("grab_window.py"));
    }

    // 2/3. 可执行文件附近（含 _up_ 子目录变体）
    if let Ok(exe) = std::env::current_exe() {
        if let Some(exe_dir) = exe.parent() {
            candidates.push(exe_dir.join("tools").join("grab_window.py"));
            candidates.push(exe_dir.join("_up_").join("tools").join("grab_window.py"));
            candidates.push(exe_dir.join("_up_").join("grab_window.py"));
            if let Some(p1) = exe_dir.parent() {
                candidates.push(p1.join("tools").join("grab_window.py"));
                if let Some(p2) = p1.parent() {
                    candidates.push(p2.join("tools").join("grab_window.py"));
                }
            }
        }
    }

    // 4. 当前工作目录
    candidates.push(PathBuf::from("tools/grab_window.py"));
    candidates.push(PathBuf::from("../tools/grab_window.py"));

    for p in candidates {
        if p.exists() {
            return Some(p);
        }
    }
    None
}

/// 查找 python 可执行文件
fn find_python() -> Option<String> {
    for cmd in ["python", "python3", "py"] {
        if let Ok(out) = Command::new(cmd).arg("--version").output() {
            if out.status.success() {
                return Some(cmd.to_string());
            }
        }
    }
    None
}

#[tauri::command]
async fn capture_and_ocr(
    app_handle: tauri::AppHandle,
    backend_url: String,
    token: String,
) -> Result<OcrResult, String> {
    // 1. 查找 Python 与脚本
    let python = find_python().ok_or_else(|| "未找到 python 可执行文件".to_string())?;
    let script =
        find_grab_script(&app_handle).ok_or_else(|| "未找到 tools/grab_window.py".to_string())?;

    // 2. 调用 Python 脚本截图（指定蓝基因/Androws 窗口）
    // 输出到临时目录，避免污染应用目录
    let tmp_dir = std::env::temp_dir();
    let output_png = tmp_dir.join(format!(
        "learning_dashboard_ocr_{}.png",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_millis())
            .unwrap_or(0)
    ));

    let mut cmd = Command::new(&python);
    cmd.arg(&script)
        .arg("--proc")
        .arg("Androws.exe")
        .arg("--title")
        .arg("蓝基因")
        .arg("--json")
        .arg("-o")
        .arg(&output_png);
    // Windows: 不显示 cmd 弹窗
    #[cfg(windows)]
    cmd.creation_flags(CREATE_NO_WINDOW);

    log::info!(
        "[capture_and_ocr] 调用 Python: {} {} -> {}",
        python,
        script.display(),
        output_png.display()
    );

    let output = cmd
        .output()
        .map_err(|e| format!("调用 Python 脚本失败: {}", e))?;

    // 解析脚本输出的最后一行 JSON
    let stdout = String::from_utf8_lossy(&output.stdout).to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).to_string();
    log::info!(
        "[capture_and_ocr] Python 退出码={} | stdout 长度={} | stderr: {}",
        output.status.code().unwrap_or(-1),
        stdout.len(),
        stderr
    );
    if !output.status.success() {
        return Ok(OcrResult {
            success: false,
            text: String::new(),
            error: Some(format!("Python 脚本执行失败: {}", stderr)),
            png_path: None,
            parsed: None,
            saved: false,
            save_error: None,
            saved_id: None,
        });
    }

    // 取最后一行非空作为 JSON
    let json_line = stdout
        .lines()
        .rev()
        .find(|l| !l.trim().is_empty())
        .unwrap_or("");

    let grab_result: serde_json::Value = match serde_json::from_str(json_line) {
        Ok(v) => v,
        Err(e) => {
            return Ok(OcrResult {
                success: false,
                text: String::new(),
                error: Some(format!("解析脚本输出失败: {} | stdout: {}", e, stdout)),
                png_path: None,
                parsed: None,
                saved: false,
                save_error: None,
                saved_id: None,
            });
        }
    };

    if !grab_result["success"].as_bool().unwrap_or(false) {
        let err = grab_result["error"]
            .as_str()
            .unwrap_or("截图失败")
            .to_string();
        return Ok(OcrResult {
            success: false,
            text: String::new(),
            error: Some(err),
            png_path: None,
            parsed: None,
            saved: false,
            save_error: None,
            saved_id: None,
        });
    }

    let png_path = grab_result["png_path"]
        .as_str()
        .unwrap_or_else(|| output_png.to_str().unwrap_or(""))
        .to_string();

    // 3. 读取 PNG 文件
    let png_bytes = match std::fs::read(&png_path) {
        Ok(b) => {
            log::info!("[capture_and_ocr] 读取截图 {} 字节", b.len());
            b
        }
        Err(e) => {
            log::error!("[capture_and_ocr] 读取截图失败: {}", e);
            return Ok(OcrResult {
                success: false,
                text: String::new(),
                error: Some(format!("读取截图文件失败: {}", e)),
                png_path: Some(png_path),
                parsed: None,
                saved: false,
                save_error: None,
                saved_id: None,
            });
        }
    };

    if png_bytes.is_empty() {
        log::error!("[capture_and_ocr] 截图文件为空");
        return Ok(OcrResult {
            success: false,
            text: String::new(),
            error: Some("截图文件为空".to_string()),
            png_path: Some(png_path),
            parsed: None,
            saved: false,
            save_error: None,
            saved_id: None,
        });
    }

    // 4. 发送到后端 OCR 接口
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(60))
        .connect_timeout(std::time::Duration::from_secs(15))
        .build()
        .map_err(|e| format!("创建 HTTP 客户端失败: {}", e))?;
    let form = reqwest::multipart::Form::new().part(
        "image",
        reqwest::multipart::Part::bytes(png_bytes)
            .file_name("screenshot.png")
            .mime_str("image/png")
            .map_err(|e| e.to_string())?,
    );

    let url = format!(
        "{}/api/v1/wrong-questions/ocr",
        backend_url.trim_end_matches('/')
    );
    let resp = client
        .post(&url)
        .header("Authorization", format!("Bearer {}", token))
        .multipart(form)
        .send()
        .await
        .map_err(|e| {
            // 打印完整错误源链，方便定位是 DNS/TLS/连接哪一步失败
            let mut msg = format!("请求失败: {}", e);
            let mut source = std::error::Error::source(&e);
            while let Some(s) = source {
                msg.push_str(&format!("\n  caused by: {}", s));
                source = s.source();
            }
            msg
        })?;

    if !resp.status().is_success() {
        let status = resp.status();
        let body = resp.text().await.unwrap_or_default();
        log::error!("[capture_and_ocr] OCR 接口返回 {}: {}", status, body);
        return Ok(OcrResult {
            success: false,
            text: String::new(),
            error: Some(format!("OCR 接口返回 {}: {}", status, body)),
            png_path: Some(png_path),
            parsed: None,
            saved: false,
            save_error: None,
            saved_id: None,
        });
    }

    let json: serde_json::Value = resp
        .json()
        .await
        .map_err(|e| format!("解析响应失败: {}", e))?;
    let text = json["text"].as_str().unwrap_or("").to_string();
    let parsed = json.get("parsed").cloned();
    log::info!(
        "[capture_and_ocr] OCR 成功，text 长度={}，parsed={}",
        text.len(),
        parsed.is_some()
    );

    // 5. Rust 端直接调用 backend 保存接口（避免前端 invoke 序列化问题导致保存丢失）
    let mut saved = false;
    let mut save_error: Option<String> = None;
    let mut saved_id: Option<i64> = None;

    if !text.is_empty() {
        let parsed_obj = parsed.clone().unwrap_or_else(|| serde_json::json!({}));
        let content_str = parsed_obj
            .get("content")
            .and_then(|v| v.as_str())
            .unwrap_or(&text)
            .to_string();
        let subject_id = parsed_obj.get("subject_id").and_then(|v| v.as_i64());
        let question_type = parsed_obj.get("question_type").and_then(|v| v.as_str());
        let answer = parsed_obj.get("answer").and_then(|v| v.as_str());

        let mut payload = serde_json::json!({ "content": content_str });
        if let Some(sid) = subject_id {
            payload["subject_id"] = sid.into();
        }
        if let Some(qt) = question_type {
            payload["question_type"] = qt.into();
        }
        if let Some(a) = answer {
            payload["answer"] = a.into();
        }

        let save_url = format!(
            "{}/api/v1/wrong-questions",
            backend_url.trim_end_matches('/')
        );
        log::info!("[capture_and_ocr] 准备保存到 {}", save_url);

        match client
            .post(&save_url)
            .header("Authorization", format!("Bearer {}", token))
            .json(&payload)
            .send()
            .await
        {
            Ok(save_resp) if save_resp.status().is_success() => {
                saved = true;
                if let Ok(save_json) = save_resp.json::<serde_json::Value>().await {
                    saved_id = save_json.get("id").and_then(|v| v.as_i64());
                }
                log::info!(
                    "[capture_and_ocr] 保存成功，id={:?}",
                    saved_id
                );
            }
            Ok(save_resp) => {
                let status = save_resp.status();
                let body = save_resp.text().await.unwrap_or_default();
                save_error = Some(format!("保存接口返回 {}: {}", status, body));
                log::error!(
                    "[capture_and_ocr] 保存失败：{} {}",
                    status,
                    body
                );
            }
            Err(e) => {
                let mut msg = format!("保存请求失败: {}", e);
                let mut source = std::error::Error::source(&e);
                while let Some(s) = source {
                    msg.push_str(&format!("\n  caused by: {}", s));
                    source = s.source();
                }
                save_error = Some(msg);
                log::error!("[capture_and_ocr] 保存请求异常: {}", e);
            }
        }
    }

    log::info!(
        "[capture_and_ocr] 完成，saved={}，saved_id={:?}",
        saved,
        saved_id
    );

    Ok(OcrResult {
        success: true,
        text,
        error: None,
        png_path: Some(png_path),
        parsed,
        saved,
        save_error,
        saved_id,
    })
}

/// 打开日志目录（用 explorer.exe）
#[tauri::command]
fn open_log_dir(app_handle: tauri::AppHandle) -> Result<String, String> {
    let log_dir = app_handle
        .path()
        .app_log_dir()
        .map_err(|e| format!("获取日志目录失败: {}", e))?;
    // 确保目录存在
    if !log_dir.exists() {
        std::fs::create_dir_all(&log_dir)
            .map_err(|e| format!("创建日志目录失败: {}", e))?;
    }
    #[cfg(windows)]
    {
        let mut cmd = Command::new("explorer.exe");
        cmd.arg(&log_dir);
        cmd.creation_flags(CREATE_NO_WINDOW);
        cmd.spawn()
            .map_err(|e| format!("打开 explorer 失败: {}", e))?;
    }
    #[cfg(not(windows))]
    {
        std::process::Command::new("open")
            .arg(&log_dir)
            .spawn()
            .map_err(|e| format!("打开文件管理器失败: {}", e))?;
    }
    Ok(log_dir.to_string_lossy().to_string())
}

fn main() {
    tauri::Builder::default()
        .plugin(
            tauri_plugin_log::Builder::new()
                .targets([
                    Target::new(TargetKind::Stdout),
                    Target::new(TargetKind::LogDir { file_name: None }),
                    Target::new(TargetKind::Webview),
                ])
                .level(log::LevelFilter::Info)
                .build(),
        )
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .setup(|app| {
            // 系统托盘：点击显示/隐藏窗口，右键显示菜单（显示/退出）
            let tray = app.tray_by_id("main").unwrap();
            let window = app.get_webview_window("main").unwrap();
            let window_clone = window.clone();
            // 托盘右键菜单
            let menu = Menu::with_items(app, &[
                &MenuItem::with_id(app, "toggle_show", "显示/隐藏", true, None::<&str>)?,
                &MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?,
            ])?;
            let _ = tray.set_menu(Some(menu));
            let app_handle_for_menu = app.handle().clone();
            tray.on_menu_event(move |app, event| match event.id().as_ref() {
                "toggle_show" => {
                    if let Some(w) = app.get_webview_window("main") {
                        if w.is_visible().unwrap_or(false) {
                            let _ = w.hide();
                        } else {
                            let _ = w.show();
                            let _ = w.unminimize();
                            let _ = w.set_always_on_top(true);
                            let _ = w.set_focus();
                            let _ = w.set_always_on_top(false);
                        }
                    }
                }
                "quit" => {
                    app_handle_for_menu.exit(0);
                }
                _ => {}
            });
            tray.on_tray_icon_event(move |_tray, event| {
                if let tauri::tray::TrayIconEvent::Click { button, button_state, .. } = event {
                    // 只响应左键按下
                    if button != tauri::tray::MouseButton::Left {
                        return;
                    }
                    if button_state != tauri::tray::MouseButtonState::Up {
                        return;
                    }
                    if window_clone.is_visible().unwrap_or(false) {
                        let _ = window_clone.hide();
                    } else {
                        let _ = window_clone.show();
                        let _ = window_clone.unminimize();
                        // 临时置顶确保激活
                        let _ = window_clone.set_always_on_top(true);
                        let _ = window_clone.set_focus();
                        let _ = window_clone.set_always_on_top(false);
                    }
                }
            });

            // 关闭窗口时阻止退出，改为最小化到系统托盘
            let window_for_close = window.clone();
            window.on_window_event(move |event| {
                if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                    api.prevent_close();
                    let _ = window_for_close.hide();
                }
            });

            // 注册全局快捷键 Alt+Q
            let app_handle = app.handle().clone();
            let gs = app.global_shortcut();
            if let Err(e) = gs.on_shortcut("Alt+Q", move |_app, _shortcut, _event| {
                let _ = app_handle.emit("shortcut-alt-q", ());
            }) {
                eprintln!("注册全局快捷键失败: {}", e);
            }

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![capture_and_ocr, open_log_dir])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
