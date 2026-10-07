from flask import Flask, render_template
import os

app = Flask(__name__)

@app.route("/")
def main():
    return render_template("index.html", flag=os.getenv("FLAG"))

if __name__ == "__main__":
    app.run("0.0.0.0", 8080, False)