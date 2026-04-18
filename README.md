# NGO Platform API

FastAPI + MongoDB Atlas backend for the NGO community platform.

---

## Project Structure

```
ngo_app/
├── main.py                  # App entry point
├── requirements.txt
├── render.yaml              # Render deployment config
├── .env.example             # Copy to .env for local dev
├── core/
│   ├── config.py            # Settings (reads .env)
│   ├── database.py          # MongoDB connection + indexes
│   └── security.py          # JWT auth, password hashing, role guards
├── routers/
│   ├── auth.py              # /auth/* — register, login, refresh
│   ├── users.py             # /users/* — profile, likes, dislikes
│   ├── volunteers.py        # /volunteers/* — skills, tasks
│   ├── ngos.py              # /ngos/* — profile, resources, donations
│   ├── problems.py          # /problems/* — CRUD + search
│   └── posts.py             # /posts/* — CRUD + upvote
└── utils/
    └── helpers.py           # ID generation, serialization
```

---

## Step-by-Step: Deploy to Render

### 1. Set up MongoDB Atlas

1. Go to https://cloud.mongodb.com and sign in / sign up (free tier works).
2. Create a new **Cluster** (M0 Free Tier is fine for development).
3. Under **Database Access** → Add a database user with a strong password.
4. Under **Network Access** → Add IP Address → **Allow Access from Anywhere** (`0.0.0.0/0`).
5. Click **Connect** → **Drivers** → copy the connection string.
   It looks like:
   ```
   mongodb+srv://<user>:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
   ```
   Replace `<user>` and `<password>`, and add the DB name before the `?`:
   ```
   mongodb+srv://myuser:mypassword@cluster0.xxxxx.mongodb.net/ngo_db?retryWrites=true&w=majority
   ```

### 2. Push code to GitHub

```bash
cd ngo_app
git init
git add .
git commit -m "Initial NGO platform API"
# Create a repo on GitHub, then:
git remote add origin https://github.com/YOUR_USERNAME/ngo-api.git
git push -u origin main
```

### 3. Deploy on Render

1. Go to https://render.com and sign in.
2. Click **New** → **Web Service**.
3. Connect your GitHub repo.
4. Render will detect `render.yaml` automatically. If not, set:
   - **Environment**: Python
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Under **Environment Variables**, add:
   | Key | Value |
   |-----|-------|
   | `MONGODB_URL` | Your Atlas connection string from Step 1 |
   | `SECRET_KEY` | Any random 32+ character string (or let Render generate it via render.yaml) |
   | `DB_NAME` | `ngo_db` |
6. Click **Create Web Service**.
7. Wait ~2 minutes. Your API will be live at:
   ```
   https://ngo-platform-api.onrender.com
   ```

### 4. Verify

Open `https://your-render-url.onrender.com/docs` in a browser.
You'll see interactive Swagger UI with all endpoints.

---

## Local Development

```bash
cd ngo_app
cp .env.example .env
# Edit .env with your MongoDB URL and a SECRET_KEY

pip install -r requirements.txt
uvicorn main:app --reload
# API at http://localhost:8000
# Docs at http://localhost:8000/docs
```

---

## Authentication Flow

All three entity types share the same login endpoint.

### Register

```
POST /auth/register/user       → regular user
POST /auth/register/volunteer  → volunteer
POST /auth/register/ngo        → NGO (requires pan_number + darpan_id)
```

### Login

```
POST /auth/login
Body: { "email": "...", "password": "...", "role": "user|volunteer|ngo" }
Returns: { "access_token": "...", "refresh_token": "...", "token_type": "bearer", "role": "..." }
```

### Refresh

```
POST /auth/refresh
Body: { "refresh_token": "..." }
Returns: new access_token
```

### Using tokens in Dart (Flutter)

```dart
// Add to every authenticated request:
headers: {
  'Authorization': 'Bearer $accessToken',
  'Content-Type': 'application/json',
}
```

---

## Key API Endpoints

### Users
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | /users/me | Any | Own profile |
| PUT | /users/me | Any | Update profile (not skills) |
| PUT | /users/me/password | Any | Change password |
| POST | /users/me/react | User/Vol | Like/dislike a problem or post |
| DELETE | /users/me | Any | Delete account |
| GET | /users/{id} | Public | View any user |

### Volunteers
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | /volunteers/ | Public | List + search by skill/level/location |
| GET | /volunteers/{id} | Public | Get volunteer |
| POST | /volunteers/skills/assign | NGO | Assign skill + level to volunteer |
| DELETE | /volunteers/skills/remove | NGO | Remove skill |
| POST | /volunteers/tasks/assign | NGO | Assign task |
| POST | /volunteers/tasks/complete | NGO | Mark task complete |
| POST | /volunteers/select/{id} | NGO | Select volunteer |
| DELETE | /volunteers/select/{id} | NGO | Deselect volunteer |

### NGOs
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | /ngos/ | Public | List NGOs |
| GET | /ngos/me | NGO | Own profile (with PAN/Darpan) |
| PUT | /ngos/me | NGO | Update profile |
| GET | /ngos/{id} | Public | Public NGO profile |
| GET | /ngos/{id}/volunteers | Public | Selected volunteers |
| POST | /ngos/me/resources | NGO | Add resource |
| DELETE | /ngos/me/resources/{id} | NGO | Remove resource |
| POST | /ngos/me/donations | NGO | Record donation to resource |
| POST | /ngos/me/partners | NGO | Add partner org to resource |

### Problems (volunteers post, everyone views)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | /problems/ | Volunteer | Create problem |
| GET | /problems/ | Public | Search (category, date, skill, level, importance) |
| GET | /problems/{id} | Public | Get problem |
| PUT | /problems/{id} | Poster | Update |
| DELETE | /problems/{id} | Poster/NGO | Delete |
| POST | /problems/{id}/volunteer | Volunteer | Join problem |

### Posts (NGO + selected volunteers post, everyone views)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | /posts/ | NGO/SelVol | Create post |
| GET | /posts/ | Public | Search (category, date, tag) |
| GET | /posts/{id} | Public | Get post |
| PUT | /posts/{id} | Poster | Update |
| DELETE | /posts/{id} | Poster/NGO | Delete |
| POST | /posts/{id}/upvote | Any | Toggle upvote |

---

## Search Examples

```
# Search problems by category and date range
GET /problems/?category=health&from_date=2024-01-01&to_date=2024-12-31

# Search problems by volunteer skill
GET /problems/?skill=first+aid&skill_level=3

# Search volunteers by skill
GET /volunteers/?skill=teaching&skill_level=4

# Search posts by category
GET /posts/?category=announcement&from_date=2024-06-01
```

---

## Data Model Summary

### User / Volunteer (shared fields)
```json
{
  "_id": "...",
  "email": "...",
  "name": "...",
  "aadhaar_id": "...",
  "date_of_birth": "1995-06-15",
  "location": "Mumbai",
  "liked": ["problem_id", "post_id"],
  "disliked": []
}
```

### Volunteer (extra fields)
```json
{
  "skills": [{"skill": "Teaching", "level": 4, "assigned_by_ngo": "ngo_id"}],
  "current_task": {"title": "...", "description": "...", "status": "active"},
  "previous_tasks": []
}
```

### NGO
```json
{
  "pan_number": "AAAPL1234C",
  "darpan_id": "MH/2020/0123456",
  "selected_volunteers": ["vol_id_1"],
  "resources": [{
    "resource_id": "...",
    "title": "Food Drive",
    "donations": [{"donor_name": "Raj", "amount": 5000, "image_proof_url": "https://..."}],
    "partner_organizations": [{"org_name": "FoodBank", "image_url": "https://..."}]
  }]
}
```

### Problem
```json
{
  "title": "Broken road near school",
  "importance": 4,
  "types": ["infrastructure", "safety"],
  "likes": ["user_id"],
  "volunteers_on_problem": ["vol_id"]
}
```
