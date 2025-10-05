# Visual Roll Call - Colégio Carbonell

The Visual Roll Call system is a web application designed to streamline the student calling process at Colégio Carbonell. The tool allows authorized users to search for students in real-time and send them to a display panel, which is instantly updated for everyone viewing it.

## 🚀 Key Features

*   **Secure Authentication:** Exclusive login for users with Google accounts from the `@colegiocarbonell.com.br` domain.
*   **Student Search:** Integrates with the Sophia management system API to search for students by name.
*   **Smart Filters:** Searches can be filtered by educational stage.
*   **Calling Terminal:** A simple interface where the user searches for a student and "calls" them with a single click.
*   **Real-Time Dashboard:** A display screen (ideal for TVs and monitors) that shows the called students. The panel updates for all connected clients in real-time.
*   **Voice Search:** The terminal has a button to perform student searches using the microphone.

## 🛠️ Tech Stack

This project is built with a combination of backend, frontend, and cloud service technologies:

### Backend:

*   **Python:** The primary programming language.
*   **Flask:** A web microframework for building the application and API.
*   **Gunicorn:** A WSGI server to run the application in production.
*   **Authlib:** For integration with Google's authentication system (OAuth).

### Frontend:

*   **HTML5 / CSS3:** For page structure and styling.
*   **JavaScript (ES6 Modules):** For client-side interactivity, such as searches, click events, and communication.

### Database and Real-Time Sync:

*   **Google Firebase (Firestore):** Used as a real-time NoSQL database to synchronize called students between the terminal and the display panel. *Note: The current `app.py` is a simplified version and does not contain the Firebase integration code, but it is a core part of the deployed application.*

## ⚙️ Project Setup

Follow these steps to set up the project for local development.

### 1. Prerequisites

*   Python 3.7+
*   pip package manager

### 2. Clone the Repository

```bash
git clone <repository-url>
cd <repository-directory>
```

### 3. Set Up a Virtual Environment

It's recommended to use a virtual environment to manage project dependencies.

```bash
# Create a virtual environment
python -m venv venv

# Activate it
# On Windows:
# venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

### 4. Install Dependencies

Install all required packages using the `requirements.txt` file.

```bash
pip install -r requirements.txt
```

### 5. Configure Environment Variables

Create a `.env` file in the root directory of the project. This file will store sensitive credentials and configuration settings. Add the following variables:

```
# Flask secret key for session management
SECRET_KEY='your_strong_secret_key_here'

# Google OAuth Credentials
GOOGLE_CLIENT_ID='your_google_client_id'
GOOGLE_CLIENT_SECRET='your_google_client_secret'

# Sophia API Credentials
SOPHIA_TENANT='your_sophia_tenant'
SOPHIA_USER='your_sophia_user'
SOPHIA_PASSWORD='your_sophia_password'
SOPHIA_API_HOSTNAME='your_sophia_api_hostname'
```

Replace the placeholder values with your actual credentials.

## 🏃‍♀️ Running the Application

### Development Mode

For development, you can use Flask's built-in server:

```bash
export FLASK_APP=app.py
export FLASK_ENV=development
flask run
```

The application will be available at `http://127.0.0.1:5000`.

### Production Mode

For production deployments, it is recommended to use a WSGI server like Gunicorn:

```bash
gunicorn --bind 0.0.0.0:8080 app:app
```

## 💻 How to Use

1.  **Login:** Access the application's URL and log in with an authorized `@colegiocarbonell.com.br` Google account.
2.  **Terminal:** After logging in, you will be directed to the **Terminal** page.
3.  **Search:** Use the search bar to find students by name. You can also apply filters for different educational stages.
4.  **Call Student:** Click on a student's name in the search results to "call" them.
5.  **Dashboard:** The called student will instantly appear on the **Dashboard** page. This page is designed to be displayed on a public screen (like a TV) and updates in real-time for all viewers.

---
*Original Developer: Thiago Marques*