# Date Fruit AI & Price Marketplace

A date-fruit variety classifier joined to a shared price marketplace. Any
registered user can photograph dates and have the AI name the variety, publish a
priced listing with that photo, browse everyone else's listings, and see which
shop is cheapest per gram.

Built as a university capstone project. It runs entirely on one ordinary
computer: **CPU only — no GPU, no Docker, no cloud services.**

The model recognises **nine** varieties, listed in `model/classes.json`:

> Ajwa · Galaxy · Medjool · Meneifi · Nabtat Ali · Rutab · Shaishe · Sokari ·
> Sugaey

---

## Contents

- [Technology used](#technology-used)
- [What you need to install](#what-you-need-to-install)
- [Setup](#setup)
- [How to start the project](#how-to-start-the-project)
- [If it will not start](#if-it-will-not-start)

---

## Technology used

These are the versions the project was actually built and run on, confirmed by
running them — not minimum requirements.

### Backend

| Purpose | Technology | Version |
|---|---|---|
| Language | Python | 3.13.3 |
| Web framework | FastAPI | 0.141.1 |
| Web server | Uvicorn (with `[standard]` extras) | 0.52.3 |
| File uploads | python-multipart | 0.0.32 |
| Database | PostgreSQL | 16.10 |
| Database toolkit (ORM) | SQLAlchemy | 2.0.52 |
| Database migrations | Alembic | 1.19.1 |
| PostgreSQL driver | psycopg (version 3, binary wheel) | 3.3.4 |
| Validation | Pydantic | 2.13.4 |
| Settings from `.env` | pydantic-settings | 2.15.0 |
| Email validation | email-validator | 2.3.0 |
| Login tokens | PyJWT | 2.13.0 |
| Password hashing | bcrypt | 5.0.0 |
| Machine learning | TensorFlow (**CPU wheel**) | 2.21.0 |
| Model format | Keras | 3.15.1 |
| Image decoding / resizing | Pillow | 12.3.0 |
| Arrays | numpy | 2.5.2 |
| Tests | pytest | 9.1.1 |
| Test HTTP client | httpx | 0.28.1 |

### Frontend

| Purpose | Technology | Version |
|---|---|---|
| JavaScript runtime | Node.js | 22.14.0 |
| Package manager | npm | 10.9.2 |
| UI library | React / react-dom | 19.2.8 |
| Build tool / dev server | Vite | 8.2.1 |
| React plugin for Vite | @vitejs/plugin-react | 6.0.4 |
| Styling | Tailwind CSS (+ `@tailwindcss/vite`) | 4.3.3 |
| Page routing | react-router-dom | 7.18.2 |
| HTTP requests | axios | 1.19.0 |
| Linter | oxlint | 1.75.0 |

**TensorFlow here is the plain CPU wheel, and that is deliberate.** Do not
replace it with a CUDA/GPU build — the project is required to run on an ordinary
laptop with no graphics card.

### How the pieces fit together

```
Browser  →  React app (Vite dev server, port 5173)
                │  axios, over HTTP
                ▼
            FastAPI  (Uvicorn, port 8000)
                ├──────────────► PostgreSQL   users · categories · listings
                ├──────────────► TensorFlow    model/date_fruit_model.keras
                └──────────────► disk          backend/uploads/listings/
```

The backend and the frontend are two separate programs. Both have to be running.

---

## What you need to install

Five things. Everything else is handled by the setup steps below.

| Requirement | Version used here | Notes |
|---|---|---|
| **Python** | 3.13.3 | On Windows, tick **"Add python.exe to PATH"** in the installer. |
| **PostgreSQL** | 16.10 | **Write down the password** you set for the `postgres` user during installation — you need it in step 4. |
| **Node.js** | 22.14.0 | npm comes with it. |
| **Git** | any | Only needed to `git clone`. Skip it if you received the folder as a ZIP or on a USB stick. |
| **The trained model** | — | `model/date_fruit_model.keras` is **338,277,666 bytes** and is **not** in the repository — it is over GitHub's 100 MiB per-file limit. Download it separately (step 1). |

Check what you already have:

```powershell
python --version
node --version
npm --version
psql --version
git --version
```

```bash
# macOS / Linux
python3 --version && node --version && npm --version && psql --version && git --version
```

### Hardware

- **CPU only.** No graphics card is needed or used.
- **8 GB of RAM is enough.** The backend process holds Python, TensorFlow and the
  loaded model, which is the largest single consumer.
- **Disk: budget about 3 GB.** Roughly 2.5 GB for the Python virtual environment
  (TensorFlow is large), 323 MiB for the model, and a few hundred MB for
  `node_modules`.

---

## Setup

Six steps, once. Commands are given for **Windows PowerShell** first, with
macOS/Linux equivalents underneath.

Run everything from the **project root** — the folder containing this README —
unless a step says otherwise.

### 1. Get the project and the model

```powershell
git clone <your-repository-url> date-fruit-project
cd date-fruit-project
```

Then put the trained model into the `model/` folder, next to the `classes.json`
that came with the clone, so the paths are exactly:

```
date-fruit-project/model/date_fruit_model.keras
date-fruit-project/model/classes.json
```

Confirm both files are present and the right size:

```powershell
Get-ChildItem model | Select-Object Name, Length
```

```bash
# macOS / Linux
ls -l model
```

You must see **both**, at exactly these sizes:

```
classes.json                        94 bytes
date_fruit_model.keras     338,277,666 bytes
```

A smaller `date_fruit_model.keras` means the download was incomplete — fetch it
again. Registration, login and the marketplace all work without the model; only
classification needs it, and it answers `503` while the model is missing.

### 2. Create the virtual environment and install the Python packages

A *virtual environment* is a private copy of Python for this project alone, so
its packages never clash with anything else on your computer.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

```bash
# macOS / Linux
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r backend/requirements.txt
```

> This downloads TensorFlow and is by far the slowest part of setup — budget
> several minutes and about 2.5 GB of disk. It is a one-time cost.

The commands call `.venv\Scripts\python.exe` directly rather than "activating"
the environment. That is deliberate throughout this README: it works whether or
not your shell allows activation scripts, and it removes any doubt about which
Python is running.

### 3. Create the database

The application creates the *tables* for you, but not the database itself.
Create the empty database first:

```powershell
psql -U postgres -c "CREATE DATABASE date_fruit_db;"
```

You will be prompted for the `postgres` password you chose when installing
PostgreSQL.

If `psql` is not recognised as a command, either add PostgreSQL's `bin` folder to
your PATH, or use the **pgAdmin** application that ships with it: right-click
*Databases* → *Create* → *Database*, and name it `date_fruit_db`.

### 4. Configure the backend

Copy the example file, then edit **the copy**. The example is committed to Git;
your copy never is.

```powershell
Copy-Item backend\.env.example backend\.env
```

```bash
# macOS / Linux
cp backend/.env.example backend/.env
```

Now open `backend/.env` and change **two** values.

**a) `DATABASE_URL`** — replace `YOUR_PASSWORD` with your real PostgreSQL
password:

```ini
DATABASE_URL=postgresql://postgres:my-real-password@localhost:5432/date_fruit_db
```

**b) `JWT_SECRET`** — this signs login tokens, so anyone who knows it could forge
a login. **The application refuses to start while it is still `CHANGE_ME`**, and
also refuses anything shorter than 32 characters. Generate a real one:

```powershell
.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

```bash
# macOS / Linux
.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Paste the output in:

```ini
JWT_SECRET=paste-the-long-random-string-here
```

Leave the other keys alone for now. For reference, the full set is:

| Key | Required | Default | What it does |
|---|---|---|---|
| `DATABASE_URL` | **Yes** | — | `postgresql://USER:PASSWORD@HOST:PORT/DATABASE`. Must be PostgreSQL — SQLite and MySQL are not supported. |
| `JWT_SECRET` | **Yes** | — | Signs login tokens. At least 32 random characters, different on every machine. |
| `JWT_EXPIRE_MINUTES` | No | `60` | How long a login lasts, in minutes. |
| `CONFIDENCE_THRESHOLD` | No | `0.70` | How confident the model must be before the API will name a variety. Must be greater than 0 and at most 1.0 — a decimal fraction, so `0.70`, never `70`. |
| `FRONTEND_URL` | No | `http://localhost:5173` | The only browser address allowed to call the API (this is the CORS setting). |

There is also `WARM_MODEL_ON_STARTUP` (default `true`), which is not in
`.env.example`. Setting it to `false` makes the server start instantly and load
the model on the first classification instead — useful on a low-memory machine,
or when you are only working on accounts and the marketplace.

### 5. Create the database tables

Alembic builds the real tables from the code. It must run **from inside
`backend/`**, because that is where `alembic.ini` lives:

```powershell
cd backend
..\.venv\Scripts\python.exe -m alembic upgrade head
cd ..
```

```bash
# macOS / Linux
cd backend && ../.venv/bin/python -m alembic upgrade head && cd ..
```

Check it worked:

```powershell
cd backend
..\.venv\Scripts\python.exe -m alembic current
cd ..
```

Expected output — the revision id followed by `(head)`:

```
579a2b2dee17 (head)
```

That single migration creates three tables — `users`, `date_fruit_categories`
and `listings` — plus the three PostgreSQL enum types they use
(`category_source`, `listing_unit`, `listing_status`) and the indexes the
marketplace price sorting relies on. It then **seeds the nine categories** by
reading `model/classes.json`, so the variety dropdowns are populated before you
add anything yourself.

### 6. Install and configure the frontend

```powershell
cd frontend
npm install
Copy-Item .env.example .env
cd ..
```

```bash
# macOS / Linux
cd frontend && npm install && cp .env.example .env && cd ..
```

`frontend/.env` needs no editing for normal local use — it already points at
`http://localhost:8000`, which is where the backend runs. It holds one key:

| Key | Default | What it does |
|---|---|---|
| `VITE_API_URL` | `http://localhost:8000` | Where the browser should reach the backend. |

Vite only exposes variables beginning with `VITE_` to browser code, so never put
a secret in this file — anything here is visible to anyone using the site.

Setup is done.

---

## How to start the project

The backend and the frontend are two separate programs, and **both must be
running**. So you need **two terminal windows**, both starting at the project
root.

### Terminal 1 — the backend API

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --app-dir backend
```

```bash
# macOS / Linux
.venv/bin/python -m uvicorn app.main:app --reload --app-dir backend
```

Wait for the line `Model ready.` before classifying anything. Startup
deliberately loads the model **and** runs one throwaway prediction, because the
very first prediction is slow — TensorFlow builds its computation graph on
demand. Doing it at boot means your first real user does not wait for it.

You may also see a couple of `oneDNN custom operations are on` lines from
TensorFlow. Those are informational, not errors.

`--reload` restarts the server whenever you edit a Python file. That is
convenient while developing, but it reloads the 323 MiB model every time, so
leave the flag off if you just want to run the app.

### Terminal 2 — the frontend

```powershell
cd frontend
npm run dev
```

Vite prints the address to open:

```
  ➜  Local:   http://localhost:5173/
```

> **Use `localhost`, not `127.0.0.1`.** The Vite dev server binds to the IPv6
> loopback address (`::1`) only, so `http://127.0.0.1:5173` will not connect
> while `http://localhost:5173` does.

### Where things are

| Address | What it is |
|---|---|
| <http://localhost:5173> | **The application. Start here.** |
| <http://localhost:8000> | The API root — a plain "it is running" message |
| <http://localhost:8000/docs> | **Interactive API documentation** (Swagger UI). Every endpoint, with an *Authorize* button and a *Try it out* form — generated from the code, so it is always accurate |
| <http://localhost:8000/api/health> | Machine-readable status of the database and the model |

`/api/health` is the first thing to check when something misbehaves. It needs no
login, on purpose — needing a working login to ask *"is the database up?"* would
defeat the point. A healthy system answers:

```json
{"status":"healthy","model_loaded":true,"database_connected":true}
```

It always returns HTTP 200 with a `status` field rather than failing outright, so
you can always read **which** part is unhealthy. `"degraded"` means one of the two
booleans is `false`.

### First run, in short

1. Open <http://localhost:5173> and choose **Register** — name, email, password
   (at least 8 characters) and a contact number. You land logged in.
2. Upload a photo of dates (JPG, JPEG, PNG or WEBP, up to 5 MB). Use any file
   from the `test_images/` folder if you have none of your own.
3. Read the variety and confidence, then **correct it if it is wrong** — you
   always get the final say before publishing.
4. Add a price, a quantity and a unit (`gram`, `kg` or `piece`), plus your shop
   name, contact number and location, and publish.
5. Open the marketplace to see your listing alongside everyone else's, and the
   per-gram price comparison across varieties.

### Stopping

Press `Ctrl+C` in each terminal.

---

## If it will not start

**Start here:** open <http://localhost:8000/api/health>. It needs no login and
tells you which half is broken. If the page does not load at all, the backend is
not running — look at terminal 1.

### The backend refuses to start

Configuration is validated before the server accepts a single request, so these
appear immediately and name their own fix.

| Message | Fix |
|---|---|
| `Configuration file not found: ...\backend\.env` | You skipped step 4. Run `Copy-Item backend\.env.example backend\.env`, then edit the copy. |
| `JWT_SECRET is still the placeholder 'CHANGE_ME'` | Generate a real secret (step 4b) and paste it into `backend/.env`. |
| `JWT_SECRET is too short (N characters)` | Same fix — use the generated value rather than something you invented. |
| `DATABASE_URL must be a PostgreSQL URL that starts with 'postgresql://'` | This project requires PostgreSQL. SQLite and MySQL are not supported. |
| `CONFIDENCE_THRESHOLD must be greater than 0 and at most 1.0, got 70` | Use a decimal fraction — `0.70`, not `70`. |

### `"database_connected": false`

1. **Is PostgreSQL running?** On Windows check *Services* for
   `postgresql-x64-16`, or run `Get-Service *postgres*`.
2. **Is the password right?** Test it directly:
   `psql -U postgres -d date_fruit_db -c "SELECT 1;"`
   If that fails, `DATABASE_URL` in `backend/.env` is wrong.
3. **Does the database exist?** `psql -U postgres -c "\l"` should list
   `date_fruit_db`. If not, go back to step 3.
4. **Special characters in your password.** A password containing `@`, `:`, `/`
   or `#` breaks the URL format, because those characters have meaning inside a
   URL. Either percent-encode them (`@` becomes `%40`) or use a simpler password.

**`relation "users" does not exist`** — the database exists but the tables do
not. Run the migration (step 5).

### `"model_loaded": false`, or classification answers `503`

Read the backend terminal; the real reason is logged there.

| Message | Meaning |
|---|---|
| `Model file not found: ...\model\date_fruit_model.keras` | The file is absent — it does not come with `git clone`. See step 1. |
| `Keras could not load ...` | The file is present but damaged, almost always an incomplete download. Check it is exactly 338,277,666 bytes and fetch it again. |
| `The model predicts 9 classes but model/classes.json lists 8 names` | `classes.json` has been edited. It must hold exactly the nine names, in the original order. Restore it from Git. |

Everything except classification keeps working while the model is unavailable —
that is intentional, so you can still develop accounts and the marketplace.

### Frontend problems

- **`Could not reach the server at http://localhost:8000`** — that is this
  application's own message. The backend is down, or `VITE_API_URL` in
  `frontend/.env` points somewhere wrong.
- **A CORS error in the browser console** (`No 'Access-Control-Allow-Origin'
  header`) — the backend accepts requests from the single address in
  `FRONTEND_URL` only. If Vite started on a different port because 5173 was
  taken, set `FRONTEND_URL` in `backend/.env` to the port Vite actually printed,
  and restart the backend.
- **Changed `frontend/.env` and nothing happened** — Vite reads it only at
  startup. Stop `npm run dev` and start it again.
- **A blank white page** — open the browser console (F12). This is almost always
  a JavaScript error rather than a backend problem.
- **`npm install` fails** — check `node --version` is 22 or newer. Failing that,
  delete `frontend/node_modules` and `frontend/package-lock.json` and try again.

### Other

- **`psql` is not recognised** — PostgreSQL's `bin` directory is not on your
  PATH. Add it, or use pgAdmin instead.
- **`[Errno 10048] address already in use`** — something already holds port 8000.
  Find it with `Get-NetTCPConnection -LocalPort 8000 -State Listen`, or start
  uvicorn on another port with `--port 8001` (and update `VITE_API_URL` and
  restart Vite to match).
