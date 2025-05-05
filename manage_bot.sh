#!/bin/bash

# Helper script to manage the gemini_bot systemd *user* service

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
    SERVICE_CONTENT=$(cat << EOF
[Unit]
Description=Telegram Gemini Image Bot (User Service)
After=network.target graphical-session.target

[Service]
WorkingDirectory=${PROJECT_DIR}

ExecStart=/home/ginto/miniconda3/envs/gemini/bin/python ${BOT_SCRIPT_PATH}

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
    *)
        echo "Usage: $0 {install|start|stop|restart|status|enable|disable|logs [num_lines]}"
        echo "  install - Creates and installs the systemd user service file."
        echo "  start   - Start the bot service."
        echo "  stop    - Stop the bot service."
        echo "  restart - Restart the bot service."
        echo "  status  - Show the current status of the service."
        echo "  enable  - Enable the service to start automatically on user login (requires linger)."
        echo "  disable - Disable the service from starting automatically on user login."
        echo "  logs    - Show the latest logs (add number for specific lines, e.g., logs 200)."
        exit 1
        ;;
esac

exit 0
