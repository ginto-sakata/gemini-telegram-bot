#!/bin/bash
# Helper script to manage the gemini_bot systemd _user_ service

# --- Configuration ---
SERVICE_NAME="gemini_bot.service"
# --- IMPORTANT: Set the name of your Conda environment ---
CONDA_ENV_NAME="gemini"

# --- Assuming this script is located in the project root directory ---
PROJECT_DIR=$(pwd)
BOT_SCRIPT_PATH="${PROJECT_DIR}/bot.py"
ENV_FILE_PATH="${PROJECT_DIR}/.env"

# --- Systemd user directory ---
USER_SYSTEMD_DIR="${HOME}/.config/systemd/user"
SERVICE_FILE_PATH="${USER_SYSTEMD_DIR}/${SERVICE_NAME}"

# --- Find Conda Path ---
# This might need adjustment depending on your Conda installation (miniconda, anaconda base)
CONDA_PATH=$(which conda)
if [ -z "$CONDA_PATH" ]; then
    echo "ERROR: 'conda' command not found in PATH."
    echo "Please ensure Conda is initialized for your shell (e.g., run 'conda init bash' and restart shell) or provide the full path."
    # Attempt common paths if 'which' fails
    if [ -f "${HOME}/miniconda3/bin/conda" ]; then
        CONDA_PATH="${HOME}/miniconda3/bin/conda"
        echo "INFO: Found Conda at ${CONDA_PATH}"
    elif [ -f "${HOME}/anaconda3/bin/conda" ]; then
        CONDA_PATH="${HOME}/anaconda3/bin/conda"
        echo "INFO: Found Conda at ${CONDA_PATH}"
    else
       echo "ERROR: Could not automatically determine Conda path."
       exit 1
    fi
fi
CONDA_BASE_DIR=$(dirname "$(dirname "$CONDA_PATH")")


# --- Helper function for user systemctl commands ---
run_systemctl_user() {
    COMMAND=$1
    echo "Running: systemctl --user $COMMAND $SERVICE_NAME"
    systemctl --user "$COMMAND" "$SERVICE_NAME"
    # Add a small delay after actions like start/stop/restart
    if [[ "$COMMAND" == "start" || "$COMMAND" == "stop" || "$COMMAND" == "restart" ]]; then
        sleep 1
    fi
}

# --- Installation Function ---
install_service() {
    echo "--- Installing systemd user service ---"

    # 1. Check if essential files exist
    if [ ! -f "$BOT_SCRIPT_PATH" ]; then
        echo "ERROR: Bot script not found at $BOT_SCRIPT_PATH"
        exit 1
    fi
     if [ ! -f "$ENV_FILE_PATH" ]; then
        echo "ERROR: Environment file not found at $ENV_FILE_PATH"
        exit 1
    fi

    # 2. Create user systemd directory if it doesn't exist
    echo "Ensuring directory exists: $USER_SYSTEMD_DIR"
    mkdir -p "$USER_SYSTEMD_DIR"

    # 3. Create the service file content using conda run
    # Using conda run is more robust than finding the env's python directly
    echo "Generating service file content..."
    # IMPORTANT: Ensure the ExecStart path correctly points to your conda environment's python executable
    # Example path: /home/youruser/miniconda3/envs/your_env_name/bin/python
    # You might need to manually verify and adjust this path based on your setup.
    # The CONDA_BASE_DIR and CONDA_ENV_NAME variables are intended to help construct this path,
    # but directly hardcoding or verifying the path is the safest approach.
    CONDA_PYTHON_EXEC="${CONDA_BASE_DIR}/envs/${CONDA_ENV_NAME}/bin/python"

    # Verify the calculated Python path exists
    if [ ! -f "$CONDA_PYTHON_EXEC" ]; then
        echo "ERROR: Conda Python executable not found at calculated path: $CONDA_PYTHON_EXEC"
        echo "Please manually edit manage_bot.sh and set the correct path in the SERVICE_CONTENT block."
        # Provide a template for manual editing
        SERVICE_CONTENT_TEMPLATE=$(cat << EOF_TEMPLATE
[Unit]
Description=Telegram Gemini Image Bot (User Service)
After=network.target graphical-session.target

[Service]
WorkingDirectory=${PROJECT_DIR}
ExecStart=/path/to/your/conda/envs/your_env_name/bin/python ${BOT_SCRIPT_PATH} <-- FIX THIS PATH
EnvironmentFile=${ENV_FILE_PATH}
Restart=on-failure
RestartSec=10s
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF_TEMPLATE
)
        echo "Template for manual editing:"
        echo "$SERVICE_CONTENT_TEMPLATE"
        exit 1
    fi


    echo "Using Conda Python executable: $CONDA_PYTHON_EXEC"

    SERVICE_CONTENT=$(cat << EOF
[Unit]
Description=Telegram Gemini Image Bot (User Service)
After=network.target graphical-session.target

[Service]
WorkingDirectory=${PROJECT_DIR}
ExecStart=${CONDA_PYTHON_EXEC} ${BOT_SCRIPT_PATH}
EnvironmentFile=${ENV_FILE_PATH}
Restart=on-failure
RestartSec=10s
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF
)

    echo "Writing service file to: $SERVICE_FILE_PATH"
    echo "$SERVICE_CONTENT" > "$SERVICE_FILE_PATH"

    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to write service file."
        exit 1
    fi

    # 5. Reload user daemon
    echo "Reloading systemd user daemon..."
    systemctl --user daemon-reload

    # 6. Inform about linger and enabling
    echo ""
    echo "--- Installation Complete ---"
    echo "IMPORTANT:"
    echo "1. To ensure the service runs even when you are logged out, enable lingering for your user:"
    echo "   sudo loginctl enable-linger $(whoami)"
    echo "   (You only need to do this once. Check status with: loginctl show-user $(whoami) | grep Linger)"
    echo "2. Enable the service to start on login:"
    echo "   systemctl --user enable $SERVICE_NAME"
    echo "   (or run: $0 enable)"
    echo "3. Start the service now:"
    echo "   systemctl --user start $SERVICE_NAME"
    echo "   (or run: $0 start)"
    echo ""
}


# --- Command Handling ---
ACTION=$1

case $ACTION in
    install)
        install_service
        ;;
    start)
        run_systemctl_user "start"
        ;;
    stop)
        run_systemctl_user "stop"
        ;;
    restart)
        run_systemctl_user "restart"
        ;;
    status)
        # Status doesn't modify state, run directly
        echo "Running: systemctl --user status $SERVICE_NAME"
        systemctl --user status "$SERVICE_NAME" --no-pager # Added --no-pager
        ;;
    enable)
        echo "Enabling service to start on user login..."
        run_systemctl_user "enable"
        ;;
    disable)
        echo "Disabling service from starting on user login..."
        run_systemctl_user "disable"
        ;;
    logs)
        COUNT=${2:-100} # Default to last 100 lines if no number given
        echo "Showing last $COUNT log lines for $SERVICE_NAME (user service) (-f to follow)..."
        journalctl --user -u "$SERVICE_NAME" -f -n "$COUNT" --no-pager
        ;;
    # --- Add the new 'run' command here ---
    run)
        echo "Restarting service '$SERVICE_NAME'..."
        run_systemctl_user "restart" # Use the helper to restart

        # Capture optional log lines argument, default to 100
        LOG_LINES=${2:-100}

        echo "Service restarted. Showing last $LOG_LINES log lines and following (press Ctrl+C to stop)..."
        # Execute the logs command directly, with -f to follow
        journalctl --user -u "$SERVICE_NAME" -f -n "$LOG_LINES" --no-pager
        ;;
    # --- End of new 'run' command ---

    *)
        echo "Usage: $0 {install|start|stop|restart|status|enable|disable|logs [num_lines]|run [num_lines]}" # Update usage
        echo "  install - Creates and installs the systemd user service file."
        echo "  start   - Start the bot service."
        echo "  stop    - Stop the bot service."
        echo "  restart - Restart the bot service."
        echo "  status  - Show the current status of the service."
        echo "  enable  - Enable the service to start automatically on user login (requires linger)."
        echo "  disable - Disable the service from starting automatically on user login."
        echo "  logs    - Show the latest logs (add number for specific lines, e.g., logs 200)."
        echo "  run     - Restarts the service and immediately shows live logs (optional number of initial lines)."
        exit 1
        ;;
esac

exit 0