# Atomberg Fan Controller

A desktop remote control for Atomberg smart fans via the Atomberg IoT Developer API.

## Features

- **Power on/off** toggle with visual feedback
- **Speed control** (1–6) with active speed indicator
- **LED toggle** for the fan's indicator light
- **Auto-detect fan state** on startup — the UI reflects the actual fan status immediately
- **Multi-device support** — switch between fans on your account
- **API quota tracking** — per-device and total daily call counters
- **Dark theme** UI built with Tkinter

## Prerequisites

- Python 3.8+
- An Atomberg smart fan with Developer Mode enabled in the Atomberg app

## Setup

1. **Clone this repo:**
   ```bash
   git clone https://github.com/<your-username>/atombergfan_controller.git
   cd atombergfan_controller
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Get your API credentials:**
   - Open the Atomberg app → Profile → Developer Options
   - Copy your **API Key** and **Refresh Token**

4. **Run the app:**
   ```bash
   python fan_control.py
   ```
   Or on Windows, double-click `atomfan.bat`.

5. **Enter credentials:**
   - On first launch, the Settings dialog will open automatically
   - Paste your API Key and Refresh Token, then click Save

## Configuration

Credentials and call counters are stored in:
```
%APPDATA%\AtombergControl\
```

## API Limits

The Atomberg Developer API allows **100 calls per day**. The app tracks usage and displays it in the footer.

## License

MIT
