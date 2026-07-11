from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import cars, makes, people, admin, user_routes, seo, newsletter

app = FastAPI()

origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:4173",
    "https://eeveecars.vercel.app",
    "https://eeveecars-mc7i63xu9-jpwilsons-projects.vercel.app",
    "https://www.evlineup.org",
    "https://evlineup.org",
    "http://evlineup.org",
    "https://ev-backend-three.vercel.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_credentials=True,
    # NOTE: access_token_ev_lineup is the legacy read-key header sent by the
    # frontend on every GET — removing it from allow_headers breaks all CORS
    # preflights and blanks the site.
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-Admin-Key",
        "access_token_ev_lineup",
    ],
)

# Register routers
app.include_router(cars.router)
app.include_router(makes.router)
app.include_router(people.router)
app.include_router(admin.router)
app.include_router(user_routes.router)
app.include_router(seo.router)
app.include_router(newsletter.router)


@app.get("/")
async def root():
    return "EV Lineup API"
