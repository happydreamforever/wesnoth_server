"""Local operator UI and authenticated native-server bridge.

The bridge is a loopback service boundary, not an Android HTTP API. The native
game integration must authenticate its transport before forwarding credentials.
"""

from datetime import timedelta
from functools import wraps
import hmac

from flask import Flask, abort, flash, g, jsonify, redirect, render_template, request, session, url_for
from flask_wtf.csrf import CSRFError, CSRFProtect
from pymongo.errors import PyMongoError
from werkzeug.exceptions import HTTPException

from .auth import AuthError, AuthService, hash_password
from .domain import AllianceService, DomainError
from .rules import CAMPAIGN_CONTENT_READY


def create_app(settings, db):
    """Create the production app without opening sockets or modifying schema."""
    if settings.host != "127.0.0.1":
        raise ValueError("The Alliance admin service must bind to 127.0.0.1.")
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=settings.secret_key,
        TRUSTED_HOSTS=["127.0.0.1", "localhost"],
        SESSION_COOKIE_NAME="alliance_admin",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_SECURE=False,  # Deliberate: HTTP is restricted to loopback.
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        SESSION_REFRESH_EACH_REQUEST=False,
        MAX_CONTENT_LENGTH=32 * 1024,
        MAX_FORM_MEMORY_SIZE=16 * 1024,
        MAX_FORM_PARTS=20,
        WTF_CSRF_TIME_LIMIT=3600,
        DEBUG=False,
    )
    auth = AuthService(db)
    domain = AllianceService(db)
    app.extensions["alliance_auth"] = auth
    app.extensions["alliance_domain"] = domain

    # Register this before CSRF protection: nonlocal requests must not perform
    # authentication or touch the database even when their body is malformed.
    @app.before_request
    def require_loopback():
        if request.remote_addr != "127.0.0.1":
            abort(403)

    csrf = CSRFProtect(app)

    @app.after_request
    def security_headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; style-src 'self'; img-src 'self'; "
            "form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
        )
        return response

    def is_internal():
        return request.path.startswith("/internal/")

    def error_response(code, message, status):
        if is_internal():
            return jsonify(error={"code": code, "message": message}), status
        # Host validation can reject a request before Flask creates a URL
        # adapter. A template using url_for would itself fail in that case.
        if request.routing_exception is not None:
            return message, status, {"Content-Type": "text/plain; charset=utf-8"}
        return render_template("error.html", message=message, status=status), status

    @app.errorhandler(CSRFError)
    def csrf_failure(_error):
        return error_response("csrf_required", "The form expired. Reload the page and try again.", 400)

    @app.errorhandler(AuthError)
    def auth_failure(error):
        status = 429 if error.code == "rate_limited" else 401
        return error_response(error.code, error.message, status)

    @app.errorhandler(DomainError)
    def domain_failure(error):
        status = {"not_found": 404, "forbidden": 403}.get(error.code, 409)
        return error_response(error.code, error.message, status)

    @app.errorhandler(PyMongoError)
    def database_failure(_error):
        app.logger.error("Alliance database operation failed; request rejected.")
        return error_response("database_unavailable", "The local database is unavailable. Try again when it is running.", 503)

    @app.errorhandler(HTTPException)
    def http_failure(error):
        messages = {
            400: "The request is invalid.", 401: "Authentication is required.",
            403: "This operation is not permitted.", 404: "The requested record was not found.",
            405: "This request method is not permitted.", 413: "The request is too large.",
            415: "A JSON request is required.",
        }
        return error_response("request_rejected", messages.get(error.code, "The request could not be processed."), error.code)

    @app.errorhandler(Exception)
    def unexpected_failure(error):
        # Exceptions from drivers can contain a connection string. Never log
        # arbitrary exception text, request bodies, cookies or authorization.
        app.logger.error("Alliance request failed (%s).", type(error).__name__)
        return error_response("internal_error", "The operation could not be confirmed. Check its status before retrying.", 500)

    def admin_required(view):
        @wraps(view)
        def guarded(*args, **kwargs):
            token = session.get("admin_token")
            if not isinstance(token, str):
                return redirect(url_for("login"))
            try:
                g.admin = auth.validate_token(token, "admin")
            except AuthError:
                session.clear()
                return redirect(url_for("login"))
            if g.admin.get("role") != "admin":
                session.clear()
                abort(403)
            return view(*args, **kwargs)
        return guarded

    def internal_route(path, *, methods=("POST",), player=True):
        def decorate(view):
            @wraps(view)
            def guarded(*args, **kwargs):
                # Browsers do not belong on this native-process interface.
                if request.headers.get("Origin") is not None:
                    abort(403)
                authorization = request.headers.get("Authorization", "")
                expected = "Bearer " + settings.bridge_secret
                if not hmac.compare_digest(authorization.encode("utf-8"), expected.encode("utf-8")):
                    abort(401)
                if request.method == "POST" and not request.is_json:
                    abort(415)
                if player:
                    token = request.headers.get("X-Player-Token", "")
                    if not token or len(token) > 256:
                        abort(401)
                    g.player = auth.validate_token(token, "player")
                    if g.player.get("role") != "player":
                        abort(403)
                return view(*args, **kwargs)
            csrf.exempt(guarded)
            app.route("/internal/v1" + path, methods=methods, provide_automatic_options=False)(guarded)
            return guarded
        return decorate

    def payload(*allowed):
        value = request.get_json()
        if not isinstance(value, dict) or set(value) - set(allowed):
            abort(400)
        return value

    def text_field(data, key, *, default=None, maximum=200):
        value = data.get(key, default)
        if not isinstance(value, str) or not value or len(value) > maximum:
            abort(400)
        return value

    def form_text(key, maximum=200):
        return text_field(request.form, key, maximum=maximum)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            try:
                result = auth.authenticate(form_text("username", 64), form_text("password", 1024), "admin")
            except AuthError as error:
                status = 429 if error.code == "rate_limited" else 401
                return render_template("login.html", error=error.message), status
            session.clear()
            session.permanent = True
            session["admin_token"] = result["token"]
            return redirect(url_for("dashboard"))
        return render_template("login.html")

    @app.post("/logout")
    @admin_required
    def logout():
        auth.revoke_token(session["admin_token"])
        session.clear()
        return redirect(url_for("login"))

    @app.get("/")
    @admin_required
    def dashboard():
        counts = {name: db[name].count_documents({}) for name in ("accounts", "teams", "areas", "game_runs")}
        runs = list(db.game_runs.find({}, {"_id": 1, "kind": 1, "state": 1, "created_at": 1}).sort("created_at", -1).limit(10))
        return render_template("dashboard.html", counts=counts, runs=runs)

    @app.get("/accounts")
    @admin_required
    def accounts():
        records = list(db.accounts.find({}, {"_id": 1, "username": 1, "role": 1, "status": 1, "leader": 1}).sort("username", 1).limit(100))
        return render_template("accounts.html", records=records)

    @app.get("/accounts/<account_id>")
    @admin_required
    def account_detail(account_id):
        return render_template("account.html", account=domain.get_account(account_id))

    @app.post("/accounts/<account_id>/status")
    @admin_required
    def account_status(account_id):
        domain.admin_set_account_status(g.admin["_id"], account_id, form_text("status", 20), form_text("reason", 500))
        flash("Account status updated. The action was recorded in the audit log.")
        return redirect(url_for("account_detail", account_id=account_id))

    @app.get("/teams")
    @admin_required
    def teams():
        records = list(db.teams.find({}, {"_id": 1, "name": 1, "area_id": 1, "captain_id": 1, "members": 1, "experience": 1, "rating": 1, "active_run_id": 1}).sort("name", 1).limit(100))
        return render_template("teams.html", records=records, areas=domain.list_areas())

    @app.post("/teams/<team_id>/area")
    @admin_required
    def team_area(team_id):
        domain.admin_move_team(g.admin["_id"], team_id, form_text("area_id", 100), form_text("reason", 500))
        flash("Team area updated. The action was recorded in the audit log.")
        return redirect(url_for("teams"))

    @app.get("/areas")
    @admin_required
    def areas():
        return render_template("areas.html", records=domain.list_areas())

    @app.post("/areas")
    @admin_required
    def create_area():
        domain.admin_create_area(g.admin["_id"], form_text("name", 64))
        flash("Area created.")
        return redirect(url_for("areas"))

    @app.get("/runs")
    @admin_required
    def runs():
        return render_template("runs.html", records=domain.list_runs(limit=100))

    @app.get("/runs/<run_id>")
    @admin_required
    def run_detail(run_id):
        return render_template("run.html", run=domain.get_run(run_id))

    @app.post("/runs/<run_id>/cancel")
    @admin_required
    def cancel_run(run_id):
        domain.admin_cancel_run(g.admin["_id"], run_id, form_text("reason", 500))
        flash("Run cancelled and its reservations released. No rewards were granted.")
        return redirect(url_for("run_detail", run_id=run_id))

    @app.get("/audit")
    @admin_required
    def audit():
        records = list(db.admin_audit.find({}, {"_id": 1, "actor_id": 1, "action": 1, "target_id": 1, "reason": 1, "created_at": 1}).sort("created_at", -1).limit(100))
        return render_template("audit.html", records=records)

    @internal_route("/health", methods=("GET",), player=False)
    def health():
        db.command("ping")
        return jsonify(status="ok", service="alliance", api_version=1,
                       game_bridge_integrated=False, campaign_content_ready=CAMPAIGN_CONTENT_READY)

    @internal_route("/register", player=False)
    def register():
        data = payload("username", "password", "starter_id")
        account = domain.register(text_field(data, "username", maximum=64), hash_password(text_field(data, "password", maximum=1024)), text_field(data, "starter_id", default="spearman", maximum=40))
        return jsonify(account=account), 201

    @internal_route("/login", player=False)
    def player_login():
        data = payload("username", "password")
        return jsonify(auth.authenticate(text_field(data, "username", maximum=64), text_field(data, "password", maximum=1024), "player"))

    @internal_route("/logout")
    def player_logout():
        payload()
        auth.revoke_token(request.headers["X-Player-Token"])
        return jsonify(status="logged_out")

    @internal_route("/me", methods=("GET",))
    def player_me():
        return jsonify(account=domain.get_account(g.player["_id"]))

    def directory_payload(*keys):
        # The native directory is a separate bounded contract. Preserve the
        # existing operator/domain routes and never accept caller identity/XP.
        data = payload(*keys)
        if set(data) != set(keys) or request.args:
            abort(400)
        return data

    @internal_route("/team-directory/areas")
    def directory_areas():
        data = directory_payload("after")
        return jsonify(domain.directory_areas(g.player["_id"], data["after"]))

    @internal_route("/team-directory/teams")
    def directory_teams():
        data = directory_payload("area_id", "after")
        return jsonify(domain.directory_teams(g.player["_id"], data["area_id"], data["after"]))

    @internal_route("/team-directory/my_team")
    def directory_my_team():
        directory_payload()
        return jsonify(team=domain.directory_my_team(g.player["_id"]))

    @internal_route("/team-directory/team_detail")
    def directory_team_detail():
        data = directory_payload("team_id")
        return jsonify(team=domain.directory_team(g.player["_id"], data["team_id"]))

    @internal_route("/team-directory/create_team")
    def directory_create_team():
        data = directory_payload("name", "area_id")
        # A reply can be lost after commit. My team resolves that uncertainty;
        # the native client must never automatically repeat this mutation.
        team = domain.directory_create_team(g.player["_id"], text_field(data, "name", maximum=64),
                                            text_field(data, "area_id", maximum=64))
        return jsonify(team=team), 201

    @internal_route("/team-directory/my_applications")
    def directory_my_applications():
        data = directory_payload("after")
        return jsonify(domain.directory_my_applications(g.player["_id"], data["after"]))

    @internal_route("/team-directory/team_applicants")
    def directory_team_applicants():
        data = directory_payload("team_id", "after")
        return jsonify(domain.directory_team_applicants(g.player["_id"], data["team_id"], data["after"]))

    @internal_route("/team-directory/apply_team")
    def directory_apply_team():
        data = directory_payload("team_id")
        return jsonify(domain.directory_apply_team(g.player["_id"], data["team_id"]))

    @internal_route("/team-directory/withdraw_application")
    def directory_withdraw_application():
        data = directory_payload("team_id")
        return jsonify(domain.directory_withdraw_application(g.player["_id"], data["team_id"]))

    @internal_route("/team-directory/approve_application")
    def directory_approve_application():
        data = directory_payload("team_id", "account_id")
        return jsonify(domain.directory_approve_application(g.player["_id"], data["team_id"], data["account_id"]))

    @internal_route("/team-directory/reject_application")
    def directory_reject_application():
        data = directory_payload("team_id", "account_id")
        return jsonify(domain.directory_reject_application(g.player["_id"], data["team_id"], data["account_id"]))

    @internal_route("/team-directory/application_decisions")
    def directory_application_decisions():
        directory_payload()
        return jsonify(domain.directory_application_decisions(g.player["_id"]))

    @internal_route("/team-directory/ack_decision")
    def directory_ack_decision():
        data = directory_payload("decision_id")
        return jsonify(domain.directory_ack_decision(g.player["_id"], data["decision_id"]))

    @internal_route("/areas", methods=("GET",))
    def player_areas():
        return jsonify(areas=domain.list_areas())

    @internal_route("/teams", methods=("GET",))
    def player_teams():
        return jsonify(teams=domain.list_teams(request.args.get("area_id", "area-1")))

    @internal_route("/teams/<team_id>", methods=("GET",))
    def player_team(team_id):
        return jsonify(team=domain.get_team(g.player["_id"], team_id))

    @internal_route("/teams")
    def player_create_team():
        data = payload("name", "area_id")
        return jsonify(team=domain.create_team(g.player["_id"], text_field(data, "name", maximum=64), text_field(data, "area_id", default="area-1", maximum=100))), 201

    @internal_route("/teams/<team_id>/join")
    def player_request_join(team_id):
        payload()
        return jsonify(team=domain.request_join(g.player["_id"], team_id))

    @internal_route("/teams/<team_id>/withdraw")
    def player_withdraw_join(team_id):
        payload()
        return jsonify(team=domain.withdraw_join(g.player["_id"], team_id))

    @internal_route("/teams/<team_id>/approve")
    def player_approve_member(team_id):
        data = payload("account_id")
        return jsonify(team=domain.approve_member(g.player["_id"], team_id, text_field(data, "account_id", maximum=100)))

    @internal_route("/teams/<team_id>/reject")
    def player_reject_member(team_id):
        data = payload("account_id")
        return jsonify(team=domain.reject_member(g.player["_id"], team_id, text_field(data, "account_id", maximum=100)))

    @internal_route("/team/leave")
    def player_leave_team():
        payload()
        return jsonify(result=domain.leave_team(g.player["_id"]))

    @internal_route("/teams/<team_id>/captain")
    def player_transfer_captain(team_id):
        data = payload("account_id")
        return jsonify(team=domain.transfer_captain(g.player["_id"], team_id, text_field(data, "account_id", maximum=100)))

    @internal_route("/leader/advance")
    def player_advance():
        data = payload("unit_type")
        return jsonify(account=domain.choose_advancement(g.player["_id"], text_field(data, "unit_type", maximum=100)))

    @internal_route("/campaigns/start")
    def player_start_campaign():
        data = payload("mission_id")
        return jsonify(run=domain.start_campaign(g.player["_id"], text_field(data, "mission_id", maximum=100))), 201

    @internal_route("/battles")
    def player_create_battle():
        data = payload("opponent_team_id", "map_id", "lineups")
        return jsonify(run=domain.create_battle(g.player["_id"],
            text_field(data, "opponent_team_id", maximum=100),
            text_field(data, "map_id", maximum=100), data.get("lineups"))), 201

    @internal_route("/runs/<run_id>", methods=("GET",))
    def player_run(run_id):
        run = domain.get_run(run_id)
        participant = any(p["account_id"] == g.player["_id"] for p in run["participants"])
        captain = db.teams.find_one({"_id": {"$in": run.get("team_ids", [])},
                                    "captain_id": g.player["_id"]}, {"_id": 1})
        if not participant and not captain:
            abort(403)
        return jsonify(run=run)

    @internal_route("/runs/<run_id>/approve")
    def player_approve_battle(run_id):
        payload()
        return jsonify(run=domain.approve_battle(g.player["_id"], run_id))

    @internal_route("/runs/<run_id>/ready")
    def player_ready(run_id):
        data = payload("ready")
        ready = data.get("ready", True)
        if type(ready) is not bool:
            abort(400)
        return jsonify(run=domain.set_ready(g.player["_id"], run_id, ready))

    @internal_route("/runs/<run_id>/start")
    def player_start_battle(run_id):
        payload()
        return jsonify(run=domain.start_battle(g.player["_id"], run_id))

    # Only the future native result adapter may call these privileged operations.
    # Possession of the bridge credential grants result authority. Never expose
    # this credential or forward these routes to a game client.
    @internal_route("/server/campaigns/<run_id>/finish", player=False)
    def server_finish_campaign(run_id):
        data = payload("outcome")
        return jsonify(settlement=domain.finish_campaign(run_id, text_field(data, "outcome", maximum=20)))

    @internal_route("/server/battles/<run_id>/finish", player=False)
    def server_finish_battle(run_id):
        data = payload("winner_team_id", "draw")
        draw = data.get("draw", False)
        winner = data.get("winner_team_id")
        if type(draw) is not bool or (winner is not None and (not isinstance(winner, str) or len(winner) > 100)):
            abort(400)
        return jsonify(settlement=domain.finish_battle(run_id, winner_team_id=winner, draw=draw))

    @internal_route("/server/runs/<run_id>/cancel", player=False)
    def server_cancel_run(run_id):
        data = payload("reason")
        return jsonify(run=domain.cancel_run(run_id, text_field(data, "reason", maximum=500)))

    return app
