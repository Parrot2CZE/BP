from sundial.controller import SundialController
from sundial.webapp import create_app

controller = SundialController()
app = create_app(controller)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)