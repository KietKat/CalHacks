import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from datetime import datetime
from helpers import apology, login_required, lookup, usd


# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    user_id = session["user_id"]

    # Record of current user, we want the latest price in the records to determine if a stock is currently making profit
    records = db.execute(
        "SELECT symbol, name, SUM(share) AS total_share, price FROM (SELECT * FROM history ORDER BY time DESC) WHERE id = ? GROUP BY symbol HAVING total_share != 0",
        user_id,
    )
    balance = db.execute("SELECT cash FROM users WHERE id = ?", user_id)[0]["cash"]

    # Find total cash of user
    total_cash = balance

    for record in records:
        new_price = float(lookup(record["symbol"])["price"])
        total_cash += record["total_share"] * new_price

    return render_template(
        "index.html", records=records, total_cash=total_cash, lookup=lookup
    )


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "GET":
        return render_template("buy.html")

    user_id = session["user_id"]
    user_info = db.execute("SELECT * FROM users WHERE id = ?", user_id)

    # From the form
    symbol = request.form.get("symbol")
    share = request.form.get("shares")

    stock_info = lookup(symbol)
    # Check number of stock validity
    if stock_info == None:
        return apology("Invalid stock", 403)

    # Check number of share
    if not share or float(share) <= 0:
        return apology("Invalid Shares", 403)

    share = float(share)

    # From stock_info


    balance = float(user_info[0]["cash"])
    price = float(stock_info["price"])


    name = stock_info["name"]

    remaining_cash = balance - price * share

    # Check if user have enough money in their account
    if remaining_cash < 0:
        return apology("Broke-ass mtfk!", 403)

    db.execute("UPDATE users SET cash = ? WHERE id = ?", remaining_cash, user_id)
    db.execute(
        "INSERT INTO history(id,type,symbol,name,share,price,time) VALUES (?,?,?,?,?,?,?)",
        user_id,
        "BUY",
        symbol,
        name,
        share,
        price,
        datetime.now()
    )
    return redirect("/")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    user_id = session["user_id"]

    transactions = db.execute("SELECT * FROM history WHERE id = ?", user_id)

    return render_template("history.html", transactions = transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "GET":
        return render_template("quote.html")

    symbol = request.form.get("symbol")
    value = lookup(symbol)

    if value == None:
        return apology("Stock Symbol not found", 403)

    return render_template(
        "quoted.html",
        name=value["name"],
        price=usd(value["price"]),
        symbol=value["symbol"],
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # Blank or existed username
        if (
            not username
            or len(db.execute("SELECT * FROM users WHERE username = ?", username)) >= 1
        ):
            return apology("invalid or unavailable username", 403)

        # Blank or not matching password
        if not password or not confirmation:
            return apology("invalid password", 403)
        if not password == confirmation:
            return apology("password not matching", 403)

        hashedPassword = generate_password_hash(password)
        db.execute(
            "INSERT INTO users (username, hash) VALUES (?,?)", username, hashedPassword
        )
        session["user_id"] = db.execute(
            "SELECT * FROM users WHERE username = ?", username
        )[0]["id"]
        return redirect("/")

    return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    user_id = session["user_id"]

    if request.method == "GET":
        list_of_owned_stock = db.execute("SELECT symbol, SUM(share) as total_share FROM history WHERE id = ? GROUP BY symbol HAVING total_share != 0",
                                         user_id
                                         )
        return render_template("sell.html", stock_list = list_of_owned_stock)

    symbol = request.form.get("symbol")
    share = float(request.form.get("shares"))

    stock_list = db.execute("SELECT SUM(share) AS total_share FROM history WHERE id = ? AND symbol = ?",
                             user_id,
                             symbol
                             )

    owned_share = float(stock_list[0]["total_share"])

    # Check if have enough share
    if owned_share < share:
        return apology("Insufficent Stock Share", 403)

    # user info
    user_info = db.execute("SELECT * FROM users WHERE id = ?", user_id)

    # After sucessfully sold, change:
    #   insert the transaction into history
    #   add relevant amount of cash to the account

    price = lookup(symbol)["price"]

    earning = share * price
    db.execute(
        "INSERT INTO history(id,type,symbol,name,share,price,time) VALUES (?,?,?,?,?,?,?)",
        user_id,
        "SELL",
        symbol,
        lookup(symbol)["name"],
        -1*share,
        price,
        datetime.now()
    )

    db.execute("UPDATE users SET cash = ? WHERE id = ?", user_info[0]["cash"] + earning, user_id)

    return redirect("/")
