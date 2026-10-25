from fastapi import APIRouter

from app.api.v1 import access, activities, audit, auth, dossiers, health, intelligence, intelligence_config, organizations, permissions, products, regulatory, roles, users

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(organizations.router)
api_router.include_router(users.router)
api_router.include_router(roles.router)
api_router.include_router(permissions.router)
api_router.include_router(access.router)
api_router.include_router(audit.router)

# --- Layer 2: Dossier & CTD Foundation ---
api_router.include_router(products.router)
api_router.include_router(regulatory.authorities_router)
api_router.include_router(regulatory.applications_router)
api_router.include_router(dossiers.router)
api_router.include_router(dossiers.ctd_router)
api_router.include_router(activities.router)

# --- Layer 3: Regulatory Intelligence Foundation ---
# NOTE: intelligence_config's routers (all prefixed /intelligence/...)
# must be registered BEFORE intelligence.router's /intelligence/{item_id}
# — otherwise "/intelligence/sources" would match {item_id}="sources"
# first and 422 on the UUID parse.
api_router.include_router(intelligence_config.sources_router)
api_router.include_router(intelligence_config.tags_router)
api_router.include_router(intelligence_config.config_router)
api_router.include_router(intelligence.router)
