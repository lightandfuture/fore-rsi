use super::*;

/// Initialize client diagnostics before server discovery or terminal attachment.
pub(crate) fn init_logging() {
    crate::logging::init_file_logging("herdr-client.log");
}

/// Run the thin client, recording failures through the launch path's diagnostics.
pub fn run_client() -> io::Result<()> {
    run_client_with_mode(None, None, "connecting to server").inspect_err(|err| {
        tracing::error!(err = %err, "terminal client failed");
    })
}

/// Attach to one terminal and retain failures before returning them to the CLI.
#[cfg(unix)]
pub fn run_terminal_attach(terminal_id: String, takeover: bool) -> io::Result<()> {
    init_logging();
    run_client_with_mode(
        Some((terminal_id, takeover)),
        Some(AttachEscapeState::default()),
        "attaching to terminal",
    )
    .inspect_err(|err| {
        tracing::error!(err = %err, "terminal attachment failed");
    })
}

#[cfg(windows)]
pub fn run_terminal_attach(_terminal_id: String, _takeover: bool) -> io::Result<()> {
    debug_assert!(!crate::platform::capabilities().direct_terminal_attach);
    Err(io::Error::new(
        io::ErrorKind::Unsupported,
        "direct terminal attach is not supported on Windows yet",
    ))
}
