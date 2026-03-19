# 🎙️ EasyTranscribe

**EasyTranscribe** is a minimalist, high-accuracy desktop speech-to-text widget. Built with Python and OpenAI's Whisper (via `faster-whisper`), it provides a "floating card" experience for instant transcription.

## ✨ Features
- **Elite Accuracy:** Uses the `base` Whisper model for reliable transcription.
- **Minimalist Widget:** A clean 280x280 square UI that sits perfectly in your screen corner.
- **Global Shortcut:** Press `Ctrl + Alt + S` to show or hide the app instantly from anywhere.
- **Persistence:** Remembers your preferred screen position.
- **Start with Windows:** Option to launch automatically when you turn on your PC.
- **Privacy First:** All transcription happens **locally** on your machine. No audio is sent to the cloud.

## 🚀 How to Install

### 1. Prerequisites
- **Python 3.8+**
- **FFmpeg:** Required by Whisper to process audio. 
  - *Windows:* Install via `choco install ffmpeg` or download from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/).

### 2. Setup
Clone the repository and install the dependencies:
```bash
git clone https://github.com/yi435/EasyTranscribe.git
cd EasyTranscribe
pip install -r requirements.txt
```

### 3. Run
```bash
python main.py
```

## ⌨️ Shortcuts
- **Ctrl + Alt + S:** Toggle visibility (Show/Hide).
- **Record/Stop:** Click the main blue button to start transcribing.

## 🛠️ Tech Stack
- **GUI:** CustomTkinter
- **STT Engine:** Faster-Whisper (OpenAI)
- **Audio:** PyAudio
- **OS Integration:** Pynput, PyWin32

---
*Created as my first coding project to solve the annoying problem of finding free, unlimited transcription tools.*
