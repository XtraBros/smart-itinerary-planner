from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    current_app
)

from helpers import account_store

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        next_url = request.args.get("next") or ""
        return render_template("auth/login.html", next_url=next_url)

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    next_url = request.form.get("next") or url_for("backend.backend_home")

    if not username or not password:
        flash("Username and password are required.", "error")
        return redirect(url_for("auth.login", next=next_url))

    account = account_store.verify_credentials(username, password)
    if not account:
        flash("Invalid credentials. Please try again.", "error")
        return redirect(url_for("auth.login", next=next_url))

    session["user_id"] = account["id"]
    account_store.set_active_account(account["id"])
    current_app.reload_runtime_for_account(account["id"])

    return redirect(next_url or url_for("backend.backend_home"))


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("auth/register.html")

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not username or not password:
        flash("Username and password are required.", "error")
        return redirect(url_for("auth.register"))
    if password != confirm_password:
        flash("Passwords do not match.", "error")
        return redirect(url_for("auth.register"))
    if account_store.get_account_by_username(username):
        flash("Username already exists.", "error")
        return redirect(url_for("auth.register"))

    base_config = dict(current_app.active_config or {})
    account_id = account_store.create_account(username, password, config=base_config, make_active=True)
    session["user_id"] = account_id
    current_app.reload_runtime_for_account(account_id)

    flash("Account created successfully.", "success")
    return redirect(url_for("backend.backend_home"))


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.pop("user_id", None)
    flash("Logged out.", "success")
    return redirect(url_for("auth.login"))
