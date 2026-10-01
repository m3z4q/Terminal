import os
import sys
import ast
import asyncio
import subprocess
import importlib.util

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.environ["8863392583:AAGxKGrdLFTHjuIv5dT4v4x1dsSlk8HE_dA"]
OWNER_ID = 8794321786

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

process = None
current_file = None
log_file = None


# Common cases where import name != pip package name
PACKAGE_MAP = {
    "cv2": "opencv-python",
    "PIL": "Pillow",
    "yaml": "PyYAML",
    "bs4": "beautifulsoup4",
    "Crypto": "pycryptodome",
    "dotenv": "python-dotenv",
    "sklearn": "scikit-learn",
    "telegram": "python-telegram-bot",
}


def get_imports(filename):
    """Extract top-level/imported module names from a Python file."""
    with open(filename, "r", encoding="utf-8", errors="ignore") as f:
        source = f.read()

    tree = ast.parse(source)
    modules = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                modules.add(name.name.split(".")[0])

        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                modules.add(node.module.split(".")[0])

    return sorted(modules)


def find_missing_packages(filename):
    imports = get_imports(filename)
    missing = []

    for module in imports:
        # Ignore standard-library modules
        if importlib.util.find_spec(module) is None:
            package = PACKAGE_MAP.get(module, module)
            missing.append((module, package))

    return missing


def install_missing_packages(filename):
    missing = find_missing_packages(filename)

    if not missing:
        return True, "✅ No missing packages."

    packages = [package for _, package in missing]

    output = [
        "📦 Missing packages detected:",
        "",
    ]

    for module, package in missing:
        output.append(f"{module} → {package}")

    output.append("")
    output.append("⬇️ Installing...")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            *packages,
        ],
        capture_output=True,
        text=True,
    )

    pip_output = (result.stdout + "\n" + result.stderr).strip()

    if result.returncode != 0:
        return False, (
            "\n".join(output)
            + "\n\n❌ Installation failed:\n"
            + pip_output[-3000:]
        )

    return True, (
        "\n".join(output)
        + "\n\n✅ Packages installed successfully."
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Access denied.")
        return

    await update.message.reply_text(
        "🤖 Bot ready.\n\n"
        "📁 `.py` file upload karo.\n"
        "🔍 Imports automatically detect honge.\n"
        "📦 Missing packages auto-install honge.\n"
        "🚀 Uske baad script start hogi.\n\n"
        "/status - process status\n"
        "/logs - latest logs\n"
        "/stop - process stop"
    )


async def receive_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    global process, current_file, log_file

    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Access denied.")
        return

    document = update.message.document

    if not document.file_name.lower().endswith(".py"):
        await update.message.reply_text(
            "❌ Sirf `.py` files allowed hain."
        )
        return

    # Stop previous process
    if process and process.returncode is None:
        process.terminate()

        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except asyncio.TimeoutError:
            process.kill()

    tg_file = await document.get_file()

    filename = os.path.basename(document.file_name)
    current_file = os.path.join(UPLOAD_DIR, filename)

    await tg_file.download_to_drive(current_file)

    await update.message.reply_text(
        f"📥 `{filename}` received.\n"
        "🔍 Imports scan kar raha hoon..."
    )

    # Install missing packages
    ok, install_output = await asyncio.to_thread(
        install_missing_packages,
        current_file,
    )

    if not ok:
        await update.message.reply_text(
            install_output[-4000:]
        )
        return

    await update.message.reply_text(
        install_output[-3000:]
    )

    log_file = current_file + ".log"

    with open(log_file, "w", encoding="utf-8") as f:
        f.write("")

    await update.message.reply_text(
        "🚀 Script start ho rahi hai..."
    )

    process = await asyncio.create_subprocess_exec(
        sys.executable,
        current_file,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=os.path.dirname(current_file),
    )

    asyncio.create_task(
        read_output(process, log_file)
    )

    await update.message.reply_text(
        f"🟢 Script started!\n\n"
        f"📄 `{filename}`\n"
        f"PID: `{process.pid}`"
    )


async def read_output(proc, filename):
    with open(
        filename,
        "a",
        encoding="utf-8",
        errors="replace"
    ) as f:

        while True:
            line = await proc.stdout.readline()

            if not line:
                break

            text = line.decode(
                errors="replace"
            )

            f.write(text)
            f.flush()


async def logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    if not log_file or not os.path.exists(log_file):
        await update.message.reply_text(
            "❌ Logs available nahi hain."
        )
        return

    with open(
        log_file,
        "r",
        encoding="utf-8",
        errors="replace"
    ) as f:
        data = f.read()

    if not data:
        data = "No output yet."

    await update.message.reply_text(
        "```text\n"
        + data[-3500:]
        + "\n```",
        parse_mode="Markdown"
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    if process and process.returncode is None:
        await update.message.reply_text(
            f"🟢 Running\n"
            f"PID: `{process.pid}`\n"
            f"File: `{current_file}`"
        )
    else:
        await update.message.reply_text(
            "🔴 No script running."
        )


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global process

    if update.effective_user.id != OWNER_ID:
        return

    if not process or process.returncode is not None:
        await update.message.reply_text(
            "ℹ️ No running process."
        )
        return

    process.terminate()

    try:
        await asyncio.wait_for(
            process.wait(),
            timeout=5
        )
    except asyncio.TimeoutError:
        process.kill()

    await update.message.reply_text(
        "🛑 Script stopped."
    )


def main():
    app = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("logs", logs)
    )

    app.add_handler(
        CommandHandler("status", status)
    )

    app.add_handler(
        CommandHandler("stop", stop)
    )

    app.add_handler(
        MessageHandler(
            filters.Document.ALL,
            receive_file
        )
    )

    print("🤖 Bot started...")
    app.run_polling()


if __name__ == "__main__":
    main()