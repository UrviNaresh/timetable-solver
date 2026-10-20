# Permanent deploy (har saal use karne ke liye) — step by step

Ek baar ye setup karo. Phir har saal sir khud naya data daal ke timetable
bana sakte hain — laptop ki zaroorat nahi, phone se bhi chalega.

Do cheezein deploy hongi:
- **Backend (solver)** — timetable banata hai (Render par, free)
- **Frontend (app)** — data daalne + TT dekhne ki website (Netlify par, free)

---

## Part 1 — Solver backend → Render

1. **github.com** → account banao (free) → **New repository** (public), naam jaise `timetable-solver`.
2. Is folder ki 5 files upload karo: `solver.py`, `server.py`, `requirements.txt`, `README.md`, `DEPLOY.md`
   (repo me "Add file → Upload files").
3. **render.com** → free account (Google se sign in kar sakte ho).
4. **New +** → **Web Service** → "Build and deploy from a Git repository" → apna repo select karo.
5. Settings:
   - Language: **Python 3**
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn server:app --host 0.0.0.0 --port $PORT`
   - Instance Type: **Free**
6. **Create Web Service** → 2–5 minute me deploy hoga → ek URL milega, jaise
   `https://timetable-solver-xxxx.onrender.com`
7. **Test:** browser me wo URL kholo → `{"ok":true,"service":"timetable-solver"}` dikhna chahiye. Bas, backend ready.

---

## Part 2 — Frontend (app) → Netlify

1. `college-timetable-website.zip` unzip karo → `index.html`, `app.js`, `style.css`.
2. **app.netlify.com/drop** kholo → poora folder **drag-drop** karo → live URL mil jayega.
3. (Free account bana ke Site settings → Change site name se naam badal sakte ho,
   jaise `gpcsurat-tt.netlify.app` — ye URL permanent rahega.)

---

## Part 3 — Dono ko jodo (ek baar)

1. Netlify wala URL kholo → wizard me **"Generate Timetable"** step par jao.
2. **"Solver backend (CP-SAT)"** box me **Render wala URL** daalo → **Save**.
3. Ab **Generate Timetable** dabao → CP-SAT solver chalega → **100% perfect timetable**.

---

## Har saal (sir ke liye)

1. Site kholo → data daalo: Setup → Academic Structure → Subjects → Faculty →
   Resources → Working Days & Time → Breaks → Teaching Assignments → Special Rules.
2. **Generate Timetable** → **Student Timetables** / **Faculty Timetables** → **Save as PDF / Print**.
3. Chhoti galti ho to **✏️ Edit Timetable** step (cell par click, ya text likh ke).

---

## Note
- Render free tier 15 min inactivity ke baad **sleep** ho jata hai — pehli request me
  30–50 second lagte hain. Seminar se pehle ek baar URL khol ke jagao.
- Solve me **1–4 minute** lag sakte hain (data ke size par). "240" = solver ko maximum
  kitne second chalna hai.
- Agar solve time-out ho jaye to **dobara Generate** dabao (search randomized hai —
  agli baar mil sakta hai).
