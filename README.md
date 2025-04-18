# DecodeRx 🧪

**AI-Powered Drug Information Explorer**  
DecodeRx lets users search for medications using voice, image, or text. It returns AI-generated summaries, dosage info, and links to active compounds.

## 🔥 Features
- 🔍 Search by name, image, or voice
- 💊 AI-generated medication summaries using GPT
- 🧬 Molecule links (connects to MoleScope AR)
- 📷 Pill image upload and recognition

## 🌐 Live Demo
[https://decodex.efraprojects.com](https://decodex.efraprojects.com)

## ⚙️ Tech Stack
- Python + Flask
- OpenAI GPT-4 API
- PIL + Tesseract (OCR)
- HTML5 + Bootstrap

## 📂 Structure
- `application.py` – Main Flask app
- `static/` – CSS and JS
- `templates/` – UI pages
- `utils/` – Helpers (OCR, summarizer)

## 🚀 Setup
```bash
pip install -r requirements.txt
python application.py
