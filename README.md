# 🎓 Intelligent Auto-Grading System

A professional-grade Python auto-grader with a modern dark-theme dashboard.

---

## 🚀 Setup & Run (3 steps)

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Start the server
```bash
python app.py
```

### 3. Open your browser
```
http://localhost:5000
```

---

## 📁 Project Structure

```
autograder/
├── app.py              ← Flask backend (execution engine + grading logic)
├── requirements.txt    ← Python dependencies
├── uploads/            ← Temp folder for student files (auto-cleaned)
└── static/
    └── index.html      ← Full frontend (single file, no build needed)
```

---

## ✨ Features

- **Drag & drop** upload of multiple `.py` student files
- **Secure sandboxed execution** via subprocess with timeout protection
- **Expected output comparison** — exact match, partial match (similarity score)
- **Test case mode** — define multiple stdin → expected output pairs
- **Leaderboard** — students ranked by marks
- **Export CSV** — download full results spreadsheet
- **Dark / Light theme toggle**
- **Execution time** measured per file
- **Error categorization** — syntax, runtime, timeout

---

## 💡 How to Use

1. Upload one or more `.py` files (drag & drop or click)
2. Either:
   - Paste the **expected output** in the text area, OR
   - Add **test cases** (stdin input + expected output pairs)
3. Set **max marks** per file (default: 100)
4. Click **▶ Run Evaluation**
5. View results, expand cards for details, export CSV

---

## 🔒 Security Notes

- Each file is executed in an isolated subprocess
- Execution is killed after **5 seconds** (timeout protection)
- Uploaded files are **deleted immediately** after evaluation
- No file is stored permanently
