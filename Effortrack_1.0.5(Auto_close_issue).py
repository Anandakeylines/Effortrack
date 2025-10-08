import sys
import os
import time
import threading
import requests
import mimetypes
import platform
import pygetwindow as gw
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, 
    QLineEdit, QMessageBox, QCheckBox, QHBoxLayout,QSystemTrayIcon, QMenu, QAction,QSplashScreen,QDesktopWidget
)
from PyQt5.QtCore import Qt, QTimer
import pyautogui
import threading
from pynput.mouse import Listener as MouseListener
from pynput.keyboard import Listener as KeyboardListener
from PyQt5.QtCore import QRunnable, pyqtSignal, QObject, QThreadPool,QThread,QStandardPaths
from PyQt5.QtNetwork import QLocalServer, QLocalSocket
from PyQt5.QtGui import QPixmap,QFont,QIcon
from PIL import ImageFilter
import json
from PyQt5.QtCore import pyqtSignal
try:
    from cryptography.fernet import Fernet
except ImportError:
    print("Warning: cryptography package not installed. Passwords will be stored in plain text.")
    Fernet = None

import ctypes




import win32com.client

def add_to_startup():
    startup_folder = os.path.join(os.getenv('APPDATA'), 'Microsoft\\Windows\\Start Menu\\Programs\\Startup')

    # If bundled with PyInstaller, sys.executable points to the EXE
    if getattr(sys, 'frozen', False):
        script_path = sys.executable
    else:
        script_path = os.path.abspath(sys.argv[0])

    shortcut_path = os.path.join(startup_folder, 'Effortrak.lnk')
    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(shortcut_path)

    shortcut.TargetPath = script_path
    shortcut.WorkingDirectory = os.path.dirname(script_path)
    shortcut.IconLocation = script_path
    shortcut.save()





def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_as_admin():
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)

from dotenv import load_dotenv
load_dotenv()

import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Global variables
USER_ID = None
ORG_ID = None
USER_NAME = None
LOGIN_TIME = None
API_BASE = None
ACCESS_TOKEN = None
DEVICE_TYPE = None


def reset_global_variables():
    """Reset all global variables to their initial state"""
    global USER_ID, ORG_ID, USER_NAME, LOGIN_TIME, ACCESS_TOKEN
    USER_ID = None
    ORG_ID = None
    USER_NAME = None
    LOGIN_TIME = None
    ACCESS_TOKEN = None
    
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

global HEADERS
HEADERS = {
    "Key": "4e1c3ee6861ac425437fa8b662651cde",
    "source": DEVICE_TYPE or "WINDOWS",
    "Content-Type": "application/json"
}

def set_device_type():
    global DEVICE_TYPE, HEADERS
    system = platform.system()
    release = platform.release()
    
    if system == "Windows":
        DEVICE_TYPE = f"WINDOWS_{release}"
    elif system == "Linux":
        DEVICE_TYPE = f"LINUX_{release}"
    elif system == "Darwin":
        DEVICE_TYPE = f"MACOS_{release}"
    else:
        DEVICE_TYPE = "DESKTOP"
        
    # Update headers with actual device type
    HEADERS["source"] = DEVICE_TYPE
    #print(f"[DEBUG] Device type detected: {DEVICE_TYPE}")
    return DEVICE_TYPE

       
set_device_type()

class LoginThread(QThread):
    # Signal emits (success, message) as separate arguments
    finished = pyqtSignal(bool, str)
    
    def __init__(self, email, password):
        super().__init__()
        self.email = email
        self.password = password
        
    def run(self):
        try:
            # Test connection first
            connected, msg = test_api_connection()
            if not connected:
                self.finished.emit(False, msg)
                return
                
            # Perform login
            result = login_user(self.email, self.password)
            if result and result[0]:  # Check if user_id exists
                self.finished.emit(True, "Login successful")
            else:
                self.finished.emit(False, "Invalid credentials")
        except Exception as e:
            self.finished.emit(False, str(e))
            
class LoginSignals(QObject):
    result = pyqtSignal(tuple)
    error = pyqtSignal(str)

class LoginWorker(QRunnable):
    def __init__(self, email, password):
        super().__init__()
        self.email = email
        self.password = password
        self.signals = LoginSignals()
        self.setAutoDelete(True)
        
    def run(self):
        try:
            # Test API connection first with timeout
            connected, message = test_api_connection()
            if not connected:
                self.signals.error.emit(f"Connection failed: {message}")
                return
                
            # Perform login
            result = login_user(self.email, self.password)
            if result[0]:  # If user_id exists
                self.signals.result.emit(result)
            else:
                self.signals.error.emit("Invalid credentials")
        except requests.exceptions.Timeout:
            self.signals.error.emit("Connection timed out")
        except requests.exceptions.RequestException as e:
            self.signals.error.emit(f"Network error: {str(e)}")
        except Exception as e:
            self.signals.error.emit(f"Unexpected error: {str(e)}")


class APIUrlWindow(QWidget):
    def __init__(self, config_manager):
        super().__init__()
        self.config = config_manager
        self.setWindowTitle("Effortrak")

        #  Changed size to match compact style
        self.setFixedSize(300, 300)

        #  Compact, modern style
        self.setStyleSheet("""
            QWidget {
                background-color: white;
                font-family: Arial, sans-serif;
            }
            QLabel {
                color: #333333;
            }
            QLineEdit {
                border: 1px solid #cccccc;
                border-radius: 6px;
                padding: 8px;
                font-size: 13px;
                min-width: 200px;
            }
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)

        # Auto-login check logic remains same
        saved_url = self.config.get("api_url")
        auto_login = self.config.get("auto_login", False)
        remember_creds = self.config.get("remember_credentials", False)
        has_credentials = self.config.get("saved_email") and self.config.get("saved_password")
        
        if saved_url and auto_login and has_credentials:
            global API_BASE
            API_BASE = saved_url.rstrip('/') + "/api/"
            self.login_window = LoginWindow(self.config)
            self.login_window.show()
            self.close()
            return
                    
        self.initUI()

    def show_login_window(self):
        self.login_window = LoginWindow(self.config)
        self.login_window.show()

    def initUI(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)  #  Smaller margins
        layout.setSpacing(12)  #  Consistent spacing
        self.setWindowIcon(QIcon(resource_path('icon.ico')))

        # --- Header ---
        header = QLabel()
        pixmap = QPixmap(resource_path('effortrak_logo.png')).scaled(
            120, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        header.setPixmap(pixmap)
        header.setAlignment(Qt.AlignCenter)

        instruction = QLabel("Please enter your application URL")
        instruction.setAlignment(Qt.AlignCenter)
        instruction.setStyleSheet("font-size: 12px; color: #555;")

        layout.addWidget(header)
        layout.addWidget(instruction)

        #  Added label above input
        url_label = QLabel("Application URL")
        url_label.setStyleSheet("font-size: 12px; color: #333; margin-top:15px; font-weight: bold;")
        layout.addWidget(url_label)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://tracker2.keylines.net")
        self.url_input.setStyleSheet("""
            QLineEdit {
                padding: 6px;
                font-size: 13px;
                border: 1px solid #ccc;
                border-radius: 6px;
            }
            QLineEdit:focus {
                border-color: #0078D7;
            }*
        """)
        layout.addWidget(self.url_input)

        # Submit button
        submit_btn = QPushButton("SUBMIT")
        submit_btn.setFixedWidth(120)  #  Match login form
        submit_btn.clicked.connect(self.set_api_url)
        self.url_input.returnPressed.connect(self.set_api_url)
        layout.addWidget(submit_btn, alignment=Qt.AlignHCenter)

        layout.addStretch()

        # Prefill saved URL if exists
        saved_url = self.config.get("api_url")
        if saved_url:
            self.url_input.setText(saved_url)

        # Footer
        footer = QLabel(f"© 2002 – {datetime.now().year} Keyline DigiTech All Rights Reserved")
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("font-size: 10px; color: #999; margin-top: 10px;")
        layout.addWidget(footer)

        self.setLayout(layout)



    def set_api_url(self):
        global API_BASE
        url = self.url_input.text().strip()
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        clean_url = url.rstrip('/')
        API_BASE = clean_url + "/api/"
        
        #print("[DEBUG] Entered set_api_url()")
        #print(f"[DEBUG] Cleaned URL: {clean_url}")
        
        self.config.set("api_url", clean_url, autosave=False)  # don't freeze
        self.config.save_config()  # save manually when you're ready
        #print("[DEBUG] Config manually saved after setting api_url")
        #print("[DEBUG] Called config.set() for api_url")

        self.close()
        self.login_window = LoginWindow(self.config)
        self.login_window.show()  
        
    def bring_to_front(self):
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized | Qt.WindowActive)
        self.activateWindow()

        
def test_api_connection():
    """Test if the API endpoint is reachable"""
    if not API_BASE:
        return False, "API URL not set"

    try:
        test_url = API_BASE.replace("/api/", "/")
        response = requests.get(test_url, timeout=(3.05, 5))  # 3.05s connect, 5s read
        return True, "Connection successful"
    except requests.exceptions.Timeout:
        return False, "Connection timed out"
    except requests.exceptions.RequestException as e:
        return False, f"Connection failed: {str(e)}"
        
            
class LoginWindow(QWidget):
    def __init__(self, config_manager):
        super().__init__()
        self.config = config_manager
        self.setWindowTitle("Effortrak")

        self.setFixedSize(300, 400)

        self.setStyleSheet("""
            QWidget {
                background-color: white;
                font-family: Arial, sans-serif;
            }
            QLabel {
                color: #333333;
            }
            QLineEdit {
                border: 1px solid #cccccc;
                border-radius: 6px;
                padding: 6px;
                font-size: 13px;
                min-width: 200px;
            }
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QCheckBox {
                font-size: 12px;
            }
        """)

        self.initUI()

        self.setWindowFlags(Qt.Window)
        self.from_logout = False  

        if self.config.get("auto_login") and self.config.get("remember_credentials") and not self.from_logout:
            QTimer.singleShot(100, self.attempt_auto_login)

    def attempt_auto_login(self):
        if not self.config.get("auto_login") or not self.config.get("remember_credentials"):
            return

        email = self.config.get("saved_email")
        password = self.config.get("saved_password")

        if not email or not password:
            return

        self.email_input.setText(email)
        self.password_input.setText("*" * len(password))
        self.submit_btn.setEnabled(False)
        self.submit_btn.setText("Logging in...")

        self.login_thread = LoginThread(email, password)
        self.login_thread.finished.connect(self.handle_login_result)
        self.login_thread.start()

    def perform_auto_login(self, email, password):
        user_id, org_id = login_user(email, password)

        if user_id:
            QTimer.singleShot(0, lambda: self.handle_successful_login(user_id, org_id))
        else:
            QTimer.singleShot(0, self.handle_failed_auto_login)

    def handle_successful_login(self, user_id, org_id):
        global USER_ID, ORG_ID
        USER_ID = user_id
        ORG_ID = org_id
        self.close()
        self.main_app = ScreenshotApp(self.config)
        self.main_app.show()

    def handle_failed_auto_login(self):
        self.submit_btn.setEnabled(True)
        self.submit_btn.setText("SUBMIT")
        
        self.password_input.clear()
        QMessageBox.warning(self, "Auto-Login Failed", "Could not log in with saved credentials")

    def initUI(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(20, 20, 20, 10)
        main_layout.setSpacing(12)
    
        self.setWindowIcon(QIcon(resource_path('icon.ico')))
    
        # --- Header Logo ---
        header = QLabel()
        pixmap = QPixmap(resource_path('effortrak_logo.png')).scaled(
            120, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        header.setPixmap(pixmap)
        header.setAlignment(Qt.AlignCenter)
    
        instruction = QLabel("Please enter your email and password")
        instruction.setAlignment(Qt.AlignCenter)
        instruction.setStyleSheet("font-size: 12px; color: #555;")
    
        main_layout.addWidget(header)
        main_layout.addWidget(instruction)
    
        # --- Form layout ---
        form_layout = QVBoxLayout()
        form_layout.setSpacing(10)
    
        # Email label
        email_label = QLabel("Email")
        email_label.setStyleSheet("font-size: 12px; color: #333; font-weight: bold;")
        form_layout.addWidget(email_label)
    
        # Email field
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("Email address")
        self.email_input.setStyleSheet("""
            QLineEdit {
                padding: 6px;
                font-size: 13px;
                border: 1px solid #ccc;
                border-radius: 6px;
            }
            QLineEdit:focus {
                border-color: #0078D7;
            }
        """)
        form_layout.addWidget(self.email_input)
        self.email_input.returnPressed.connect(lambda: self.password_input.setFocus())
    
        # Password label
        password_label = QLabel("Password")
        password_label.setStyleSheet("font-size: 12px; color: #333; font-weight: bold;")
        form_layout.addWidget(password_label)
    
        # Password field with eye icon INSIDE
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setStyleSheet("""
            QLineEdit {
                padding: 6px;
                font-size: 13px;
                border: 1px solid #ccc;
                border-radius: 6px;
            }
            QLineEdit:focus {
                border-color: #0078D7;
            }
        """)
        self.toggle_password_action = self.password_input.addAction(
            QIcon(resource_path("eye-closed.png")),
            QLineEdit.TrailingPosition
        )
        self.toggle_password_action.triggered.connect(self.toggle_password_visibility)
    
        form_layout.addWidget(self.password_input)
        main_layout.addLayout(form_layout)
    
        # Auto-login
        self.auto_login_check = QCheckBox("Remember me")
        self.auto_login_check.setChecked(self.config.get("auto_login", False))
        self.auto_login_check.setStyleSheet("font-size: 12px; font-weight: bold;")
        main_layout.addWidget(self.auto_login_check)
    
        # Submit button
        self.submit_btn = QPushButton("SUBMIT")
        self.submit_btn.setDefault(True)   # Pressing Enter triggers submit
        self.submit_btn.setFixedWidth(120)
        self.submit_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px;
                margin-bottom: 15px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.submit_btn.clicked.connect(self.handle_login)
        # Connect Enter key to submit
        self.password_input.returnPressed.connect(self.handle_login)
        main_layout.addWidget(self.submit_btn, alignment=Qt.AlignHCenter)
    
        # --- URL Section ---
        current_url = self.config.get("api_url", "Not set")
        self.api_url_display = QLabel(f"<span style='color: gray; '>Current URL:<span style='font-weight:600; color: #3F3F3F'> {current_url}</span></span>")
        self.api_url_display.setTextFormat(Qt.RichText)
        self.api_url_display.setAlignment(Qt.AlignLeft)
    
        link_row_layout = QHBoxLayout()
        link_row_layout.setContentsMargins(0, 0, 0, 0)
        link_row_layout.setSpacing(5)
    
        change_url = QLabel("<a href='#' style='text-decoration:none; font-weight:600; '>Change URL?</a>")
        change_url.setTextFormat(Qt.RichText)
        change_url.setTextInteractionFlags(Qt.TextBrowserInteraction)
        change_url.linkActivated.connect(self.change_api_url)
    
        mobile_login = QLabel("<a href='#' style='text-decoration:none; font-weight:600; '>Login with Mobile OTP</a>")
        mobile_login.setTextFormat(Qt.RichText)
        mobile_login.setTextInteractionFlags(Qt.TextBrowserInteraction)
        mobile_login.linkActivated.connect(self.open_otp_login)
    
        link_row_layout.addWidget(change_url)
        link_row_layout.addStretch()
        link_row_layout.addWidget(mobile_login)
    
        main_layout.addWidget(self.api_url_display)
        main_layout.addLayout(link_row_layout)
    
        # Footer
        footer = QLabel(f"© 2002 – {datetime.now().year} Keyline DigiTech All Rights Reserved")
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("font-size: 10px; color: #999; margin-top: 10px;")
        main_layout.addStretch()
        main_layout.addWidget(footer)
    
        self.setLayout(main_layout)
    #===============================================================
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self.auto_login_check.hasFocus():  # If checkbox focused → submit
                self.handle_login()
        super().keyPressEvent(event)
   #================================================================

    def toggle_password_visibility(self):
        if self.password_input.echoMode() == QLineEdit.Password:
            self.password_input.setEchoMode(QLineEdit.Normal)
            self.toggle_password_action.setIcon(QIcon(resource_path('eye-open.png')))
        else:
            self.password_input.setEchoMode(QLineEdit.Password)
            self.toggle_password_action.setIcon(QIcon(resource_path('eye-closed.png')))

    def handle_login(self):
        email = self.email_input.text().strip()
        password = self.password_input.text().strip()

        if not email or not password:
            QMessageBox.warning(self, "Error", "Please enter both email and password")
            return

        #print("[DEBUG] Login button clicked")
        self.set_ui_enabled(False)
    
        self.login_thread = LoginThread(email, password)
        self.login_thread.finished.connect(self.handle_login_result)
        self.login_thread.start()
        
    def handle_login_result(self, success, message):
        self.set_ui_enabled(True)

        if success:
            email = self.email_input.text().strip()
            password = self.password_input.text()
            
            if "*" in password:
                password = self.config.get("saved_password")
                
            auto = self.auto_login_check.isChecked()
            
            self.config.set("saved_email", email, autosave=False)
            self.config.set("saved_password", password, autosave=False)
            self.config.set("remember_credentials", True, autosave=False)
            self.config.set("auto_login", auto, autosave=False)

            self.config.save_config()

            #print("[DEBUG] Config forcibly saved after login")
            
            global USER_ID, ORG_ID
            USER_ID, ORG_ID = login_user(email, password)
            self.close()
            self.main_app = ScreenshotApp(self.config)
            self.main_app.show()
        else:
            self.email_input.setStyleSheet("border: 2px solid red;")
            self.password_input.setStyleSheet("border: 2px solid red;")

            QMessageBox.warning(self, "Login Failed", f"{message}")  

    def handle_login_error(self, error):
        self.set_ui_enabled(True)
        QMessageBox.critical(self, "Error", f"Login failed: {error}")
        
    def set_ui_enabled(self, enabled):
        self.email_input.setEnabled(enabled)
        self.password_input.setEnabled(enabled)
        self.auto_login_check.setEnabled(enabled)
        self.submit_btn.setEnabled(enabled)
        self.submit_btn.setText("SUBMIT" if enabled else "Logging in...")
    
        if enabled:
            QApplication.restoreOverrideCursor()
        else:
            QApplication.setOverrideCursor(Qt.WaitCursor)
    
        QApplication.processEvents()
        
    def open_otp_login(self):
        self.close()
        self.otp_window = OTPLoginWindow(self.config)
        self.otp_window.show()

    def change_api_url(self):
        self.close()
        self.api_window = APIUrlWindow(self.config)
        self.api_window.show()
        
    def closeEvent(self, event):
        if hasattr(self, 'login_thread') and self.login_thread.isRunning():
            self.login_thread.quit()
            self.login_thread.wait(1000)
        event.accept()
        
    
    def bring_to_front(self):
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized | Qt.WindowActive)
        self.activateWindow()

def login_user(email, password):
    global USER_NAME, LOGIN_TIME, ACCESS_TOKEN
    payload = {
        "email": email,
        "password": password,
        "device_token": "windows_pyqt",
        "fcm_token": "dummy_fcm"
    }
    
    try:
        if not API_BASE:
            raise ValueError("API base URL is not set")
            
        #logger.info(f"Attempting login for email: {email}")
        response = requests.post(
            API_BASE + "signin",
            headers=HEADERS,
            json=payload,
            timeout=(3.05, 10) 
        )
        #logger.debug(f"Login response status: {response.status_code}")
        #print(f"[DEBUG] Login response status: {response.status_code}")
        response.raise_for_status()
         
        data = response.json()
        if not data.get("success"):
            #logger.error(f"Login failed. Response: {data}")
            #print(f"Login failed. Response: {data}")
            return None, None
            
        user_data = data["data"]
        USER_NAME = user_data.get("name", "Employee")
        LOGIN_TIME = datetime.now().strftime("%H:%M")
        ACCESS_TOKEN = user_data["app_access_token"]
        #logger.info(f"Login successful for user: {USER_NAME}")
        return user_data["user_id"], user_data.get("org_id", 1)
        
    except Exception as e:
        #logger.error(f"Login error: {str(e)}")
        #print(f"Login error: {str(e)}")
        return None, None
    

class OTPLoginWindow(QWidget):
    def __init__(self, config_manager):
        super().__init__()
        self.config = config_manager
        self.setWindowTitle("Effortrak - OTP Login")
        self.setFixedSize(300, 450)  # Match other windows
        self.setStyleSheet("""
            QWidget {
                background-color: white;
                font-family: Arial, sans-serif;
            }
        """)
        self.otp_sent = False
        self.initUI()

    def initUI(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(12)
        self.setWindowIcon(QIcon(resource_path('icon.ico')))

        # --- Logo ---
        header = QLabel()
        pixmap = QPixmap(resource_path('effortrak_logo.png')).scaled(
            120, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        header.setPixmap(pixmap)
        header.setAlignment(Qt.AlignCenter)

        instruction = QLabel("Login with Mobile OTP")
        instruction.setAlignment(Qt.AlignCenter)
        instruction.setStyleSheet("font-size: 12px; color: #555; margin-bottom: 10px;")

        # --- Phone label & input ---
        phone_label = QLabel("Mobile Number")
        phone_label.setStyleSheet("font-size: 12px; color: #333; font-weight: bold;")
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("Enter your mobile number")
        self.phone_input.setStyleSheet("""
            QLineEdit {
                padding: 6px;
                font-size: 13px;
                border: 1px solid #ccc;
                border-radius: 6px;
            }
            QLineEdit:focus {
                border-color: #0078D7;
            }
        """)

        # --- OTP label & input ---
        otp_label = QLabel("OTP")
        otp_label.setStyleSheet("font-size: 12px; color: #333; font-weight: bold;")
        self.otp_input = QLineEdit()
        self.otp_input.setPlaceholderText("Enter OTP")
        self.otp_input.setEchoMode(QLineEdit.Password)
        self.otp_input.setEnabled(False)
        self.otp_input.setStyleSheet("""
            QLineEdit {
                padding: 6px;
                font-size: 13px;
                border: 1px solid #ccc;
                border-radius: 6px;
            }
            QLineEdit:focus {
                border-color: #0078D7;
            }
        """)

        # --- Buttons ---
        self.send_btn = QPushButton("Send OTP")
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.send_btn.clicked.connect(self.send_otp)

        self.verify_btn = QPushButton("Login")
        self.verify_btn.setEnabled(False)
        self.verify_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 13px;
            }
            
            QPushButton:hover:enabled {
                background-color: #45a049;
            }
        """)
        self.verify_btn.clicked.connect(self.verify_otp)

        back_btn = QPushButton("Back to Password Login")
        back_btn.setStyleSheet("""
            QPushButton {
                background-color: #e0e0e0;
                color: #333;
                border: none;
                padding: 8px;
                margin-top: 20px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #d5d5d5;
            }
        """)
        back_btn.clicked.connect(self.back_to_login)

        # --- Add widgets to main layout ---
        main_layout.addWidget(header)
        main_layout.addWidget(instruction)
        main_layout.addWidget(phone_label)
        main_layout.addWidget(self.phone_input)
        main_layout.addWidget(self.send_btn)
        main_layout.addWidget(otp_label)
        main_layout.addWidget(self.otp_input)
        main_layout.addWidget(self.verify_btn)
        main_layout.addWidget(back_btn)

        # Footer
        footer = QLabel(f"© 2002 – {datetime.now().year} Keyline DigiTech All Rights Reserved")
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("font-size: 10px; color: #999; margin-top: 10px;")
        main_layout.addStretch()
        main_layout.addWidget(footer)

        self.setLayout(main_layout)



    def send_otp(self):
        phone = self.phone_input.text().strip()
        if not phone.isdigit() or len(phone) < 10:
            QMessageBox.warning(self, "Invalid", "Enter a valid 10-digit phone number.")
            return
        try:
            url = API_BASE + "signin-with-mobile"
            payload = {"phone": phone}
            response = requests.post(url, headers=HEADERS, json=payload)
            #print("[DEBUG] OTP Send:", response.status_code, response.text)
            if response.status_code == 200 and response.json().get("success"):
                QMessageBox.information(self, "OTP Sent", "OTP sent successfully to your phone.")
                self.otp_input.setEnabled(True)
                self.verify_btn.setEnabled(True)
            else:
                QMessageBox.critical(self, "Error", "Failed to send OTP.")
        except Exception as e:
            QMessageBox.critical(self, "Exception", str(e))

    def verify_otp(self):
        phone = self.phone_input.text().strip()
        otp = self.otp_input.text().strip()
        try:
            url = API_BASE + "signin-validate-mobile"
            payload = {
                "phone": phone,
                "otp": otp,
                "device_token": "windows_pyqt",
                "fcm_token": "dummy_fcm"
            }
            response = requests.post(url, headers=HEADERS, json=payload)
            #print("[DEBUG] OTP Verify:", response.status_code, response.text)
            if response.status_code == 200 and response.json().get("success"):
                data = response.json()["data"]
                global USER_ID, ORG_ID, USER_NAME, LOGIN_TIME, ACCESS_TOKEN
                USER_ID = data["user_id"]
                ORG_ID = data.get("org_id", 1)
                USER_NAME = data.get("name", "Employee")
                LOGIN_TIME = datetime.now().strftime("%H:%M")
                ACCESS_TOKEN = data.get("app_access_token")  # ✅ now correctly placed
                self.close()
                self.main_app = ScreenshotApp(self.config)
                self.main_app.show()
            else:
                QMessageBox.critical(self, "Invalid", "Incorrect OTP.")
        except Exception as e:
            QMessageBox.critical(self, "Exception", str(e))


    def back_to_login(self):
        self.close()
        self.login_window = LoginWindow(self.config)
        self.login_window.show()

def send_screenshot(user_id, org_id, file_path=None, idle_status=1):
    if not API_BASE or not ACCESS_TOKEN:
        #logger.error("API base or token not set for screenshot upload")
        #print("[ERROR] API base or token not set")
        return False   # ### CHANGE: return False if no API or token

    url = API_BASE.replace("/api/", "/api/screenshot/upload")
    #logger.debug(f"Uploading screenshot to: {url}")
    #print(f"[DEBUG] Uploading to: {url}")

    try:
        active_window = gw.getActiveWindow()
        app_name = active_window.title if active_window else "Unknown Application"
    except Exception as e:
        #print(f"[WARNING] Could not get active window: {str(e)}")
        app_name = "Effortrak Screenshot App"

    data = {
        "user_id": str(user_id),
        "org_id": str(org_id),
        "app_name": app_name[:100],
        "app_url": "",
        "idle_status": int(idle_status),
        "is_idle_notification": "true" if idle_status else "false"
    }
    #print(f"[DEBUG] Payload data: {data}")
    #logger.debug(f"Screenshot payload data: {data}")

    headers = {
        "Key": "4e1c3ee6861ac425437fa8b662651cde",
        "source": DEVICE_TYPE or "DESKTOP",
        "Authorization": ACCESS_TOKEN
    }

    if not file_path or not os.path.exists(file_path):
        #print(f"[ERROR] Screenshot file not found: {file_path}")
        #logger.error(f"Missing screenshot file: {file_path}")
        return False   # ### CHANGE: return False if file missing

    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        mime_type = "image/jpeg"

    try:
        with open(file_path, 'rb') as f:
            files = {
                'image': (os.path.basename(file_path), f, mime_type)
            }
            response = requests.post(url, headers=headers, data=data, files=files)

        #logger.info(f"Upload response - Status: {response.status_code}, Response: {response.text}")
        #print("[API] Upload response:", response.status_code, response.text)

        # ### CHANGE: return True only if upload was successful
        if response.status_code == 201 :
            return True
        else:
            return False

    except Exception as e:
        #print("[ERROR] Upload failed:", str(e))
        #logger.error(f"Upload error: {str(e)}")
        return False   # ### CHANGE: return False on exception

class IdleMonitor(threading.Thread):
    def __init__(self, parent):
        super().__init__(daemon=True)
        self.parent = parent
        self.last_activity = time.time()
        self.running = threading.Event()
        self.running.set()
        self.lock = threading.Lock()

    def run(self):
        while self.running.is_set():
            with self.lock:
                idle_time = time.time() - self.last_activity

            # ✅ emit signal instead of updating UI directly
            self.parent.idle_signal.emit(idle_time)

            time.sleep(1)

    def stop(self):
        self.running.clear()

    # ✅ this fixes your AttributeError
    def report_activity(self):
        with self.lock:
            self.last_activity = time.time()



class InputListener:
    def __init__(self, idle_monitor):
        self.idle_monitor = idle_monitor
        self.mouse_listener = None
        self.keyboard_listener = None
        
    def start(self):
        def on_activity(*args, **kwargs):
            self.idle_monitor.report_activity()

        self.mouse_listener = MouseListener(on_move=on_activity, on_click=on_activity)
        self.keyboard_listener = KeyboardListener(on_press=on_activity)

        self.mouse_listener.start()
        self.keyboard_listener.start()
        
    def stop(self):
        if self.mouse_listener and self.mouse_listener.running:
            self.mouse_listener.stop()
            self.mouse_listener.join(timeout=1)
        if self.keyboard_listener and self.keyboard_listener.running:
            self.keyboard_listener.stop()
            self.keyboard_listener.join(timeout=1)

        
class ScreenshotApp(QWidget):
    idle_signal = pyqtSignal(float)   # ✅ class-level definition

    def __init__(self, config_manager):
        super().__init__()
        
        # ✅ connect it here
        self.idle_signal.connect(self.update_idle_state)

        self.config = config_manager
        self.setWindowTitle("Effortrak")
        self.setFixedSize(300, 500)
        self.setStyleSheet("background-color: white;")
        self.mouse_listener = None
        self.keyboard_listener = None
        self.screenshot_active = False
        self.thread = None
        self.idle_seconds = 0
        self.screenshot_interval = 300  # 300 seconds
        self.idle_threshold = 180       # 180 seconds
        self.was_idle = False
        self._force_close = False
        self.last_input_time = time.time()

        # idle timer (1-second loop)
        self.idle_timer = QTimer()
        self.idle_timer.timeout.connect(self.reset_idle_timer)
        self.idle_timer.start(1000)

        self.tray_icon = None
        self.create_tray_icon()
        self.initUI()

        # start button automatically pressed
        QTimer.singleShot(100, self.toggle_btn.click)

        set_device_type()

        # ✅ start IdleMonitor
        self.idle_monitor = IdleMonitor(self)
        self.idle_monitor.start()

        # input listener
        self.input_listener = InputListener(self.idle_monitor)
        self.input_listener.start()

        self.load_window_geometry()
        self.setAttribute(Qt.WA_DeleteOnClose)
        self._shutting_down = False

    
    def load_window_geometry(self):
        geometry = self.config.get("window_geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def save_window_geometry(self):
        self.config.set("window_geometry", self.saveGeometry())    
    
    def update_idle_display(self, idle_time):
        mins, secs = divmod(int(round(idle_time)), 60)
        self.idle_label.setText(f"Idle for: {mins:02}:{secs:02}")
        
        is_idle = idle_time >= self.idle_threshold
        
        # Update UI and state only when idle status changes
        if is_idle != self.was_idle:
            self.was_idle = is_idle
            if is_idle:
                self.tray_icon.setIcon(QIcon(resource_path("yellow-icon.ico")))
                self.active_circle.setText("Idle")
                self.active_circle.setStyleSheet("""
                    background-color: #42A5F5; 
                    color: white; 
                    font-size: 20px; 
                    border-radius: 75px;
                """)
            else:
                self.tray_icon.setIcon(QIcon(resource_path("icon.ico")))
                self.active_circle.setText("Running")
                self.active_circle.setStyleSheet("""
                    background-color: #4CAF50; 
                    color: white; 
                    font-size: 20px; 
                    border-radius: 75px;
                """)
        
    '''def set_device_type(self):
        global DEVICE_TYPE, HEADERS
        system = platform.system()
        release = platform.release()
        
        if system == "Windows":
            DEVICE_TYPE = f"WINDOWS_{release}"
        elif system == "Linux":
            DEVICE_TYPE = f"LINUX_{release}"
        elif system == "Darwin":
            DEVICE_TYPE = f"MACOS_{release}"
        else:
            DEVICE_TYPE = "DESKTOP"
            
        # Update headers with actual device type
        HEADERS["source"] = DEVICE_TYPE
        print(f"[DEBUG] Device type detected: {DEVICE_TYPE}")'''
    

    def initUI(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(15, 15, 15, 15)
        self.setWindowIcon(QIcon(resource_path('icon.ico')))

        header = QLabel()
        # Load and scale the pixmap
        pixmap = QPixmap(resource_path('effortrak_logo.png')).scaled(150, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        header.setPixmap(pixmap)
        header.setAlignment(Qt.AlignCenter)

        
       
        version = QLabel("(V1.0.5)")
        version.setFont(QFont("Arial", 8))
      
        
        version.setStyleSheet("""
    QLabel {
        margin-left: 0px;
        padding-top: 20px;
        font-size: 8pt;
        font-family: Arial;
    }
""")

        header_layout = QHBoxLayout()
        header_layout.addWidget(header)
        header_layout.addWidget(version)
        main_layout.addLayout(header_layout)
        
         # Combine name and checked-in into a single QLabel
        user_info = QLabel(f"""
    <div style='
        font-weight: 400;
        border-radius: 8px;
        padding: 8px 12px;
        display: inline-block;
        font-size: 11pt;
    '>
        {USER_NAME}
    </div><br>
    <span style='color:gray; font-size:10pt;'>Checked in today at {LOGIN_TIME} hrs</span>
""")
        user_info.setTextFormat(Qt.RichText)
        user_info.setAlignment(Qt.AlignLeft)
        main_layout.addWidget(user_info)

        # Status Circle
        self.active_circle = QLabel("Inactive")
        self.active_circle.setAlignment(Qt.AlignCenter)
        self.active_circle.setFixedSize(150, 150)
        self.active_circle.setStyleSheet("""
            background-color: #A9A9A9; 
            color: white; 
            font-size: 20px; 
            border-radius: 75px;
        """)
        main_layout.addWidget(self.active_circle, alignment=Qt.AlignCenter)

        # Idle time label
        self.idle_label = QLabel("Idle for: 00:00")
        self.idle_label.setAlignment(Qt.AlignCenter)

       # Apply improved CSS styling(change by Ananda)
        self.idle_label.setStyleSheet("""
    QLabel {
        font-size: 16px;
        font-weight: bold;
        color: #333;
        padding: 8px 16px;
        margin: 10px;
    }
""")

        main_layout.addWidget(self.idle_label)

        # Single toggle button (Start/Stop)
        self.toggle_btn = QPushButton("Start")
        self.toggle_btn.setStyleSheet("""
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #43cea2, stop:1 #185a9d);
    color: white;
    font-size: 16px;
    font-weight: 600;
    border: none;
    border-radius: 25px;
    padding: 14px 36px;
    min-width: 130px;
    box-shadow: 0px 6px 12px rgba(0, 0, 0, 0.25);
    transition: all 0.2s ease-in-out;
}

QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #32d3a5, stop:1 #1572b0);
    transform: scale(1.03);
}

QPushButton:pressed {
    background-color: #105a8d;
    padding-top: 16px;
    padding-bottom: 10px;
    box-shadow: 0px 3px 6px rgba(0, 0, 0, 0.3);
}
""")


        self.toggle_btn.clicked.connect(self.toggle_screenshot)
        main_layout.addWidget(self.toggle_btn, alignment=Qt.AlignCenter)

        # Logout button
        logout_btn = QPushButton("LOGOUT")
        logout_btn.setStyleSheet("""
    QPushButton {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 #ff5f6d, stop:1 #ffc371);
        color: white;
        font-size: 15px;
        font-weight: bold;
        border: none;
        border-radius: 25px;
        padding: 12px 30px;
        min-width: 120px;
    }
    QPushButton:hover {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 #ff3b50, stop:1 #ffb347);
    }
    QPushButton:pressed {
        background-color: #e94e4f;
        padding-top: 14px;
        padding-bottom: 10px;
    }
""")

        logout_btn.clicked.connect(self.logout)
        main_layout.addWidget(logout_btn)

        self.setLayout(main_layout)

    def create_tray_icon(self):
        # Create the tray icon
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon(resource_path("icon.ico"))) # Make sure you have an icon file
        
        # Create a context menu
        tray_menu = QMenu()
        
        # Toggle action
        self.toggle_action = QAction("Start", self)
        self.toggle_action.triggered.connect(self.toggle_screenshot)
        tray_menu.addAction(self.toggle_action)
        
        # Open action
        open_action = QAction("Open", self)
        open_action.triggered.connect(self.show_normal)
        tray_menu.addAction(open_action)
        
        # Logout action
        logout_action = QAction("Logout", self)
        logout_action.triggered.connect(self.logout)
        tray_menu.addAction(logout_action)
        
        # Exit action
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(QApplication.instance().quit)
        tray_menu.addAction(exit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.tray_icon_activated)
        self.tray_icon.show()
        
    def tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:  # Left click
            self.show_normal()

    def show_normal(self):
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized | Qt.WindowActive)
        self.activateWindow()
        
    def closeEvent(self, event):
        # Minimize to tray instead of closing
        event.ignore()
        self.hide()
        self.tray_icon.showMessage(
            "Effortrak",
            "Application is still running in the system tray",
            QSystemTrayIcon.Information,
            2000
        )



    def toggle_screenshot(self):
        if not self.screenshot_active:
            #logger.info("Starting screenshot capture")

            # Make sure old thread is fully stopped before starting new one
            if self.thread and self.thread.is_alive():
                self.screenshot_active = False
                self.thread.join(timeout=3)  # wait longer, more reliable

            # Double-check thread is dead before proceeding
            if self.thread and self.thread.is_alive():
                #logger.warning("Previous screenshot thread is still alive — aborting start")
                return

            # Start new capture thread
            self.screenshot_active = True
            self.active_circle.setText("Running")
            self.active_circle.setStyleSheet("""
                background-color: #4CAF50; 
                color: white; 
                font-size: 20px; 
                border-radius: 75px;
            """)
            self.toggle_btn.setText("Stop")
            self.toggle_action.setText("Stop")

            self.thread = threading.Thread(target=self.screenshot_loop, daemon=True)
            self.thread.start()
            self.tray_icon.setIcon(QIcon(resource_path("icon.ico")))

        else:
            #logger.info("Stopping screenshot capture")
            self.screenshot_active = False

            # Wait until thread really stops
            if self.thread and self.thread.is_alive():
                self.thread.join(timeout=3)

            if self.thread and self.thread.is_alive():
                print("Screenshot thread did not stop cleanly")

            self.active_circle.setText("Inactive")
            self.active_circle.setStyleSheet("""
                background-color: #A9A9A9; 
                color: white; 
                font-size: 20px; 
                border-radius: 75px;
            """)
            self.toggle_btn.setText("Start")
            self.toggle_action.setText("Start")
            self.tray_icon.setIcon(QIcon(resource_path("red-icon.ico")))

            

    def logout(self):
        #print("Logging out...")
        #logger.info("User initiated logout")
        self._shutting_down = True
        
        # Disable auto-login for next time
        self.config.set("auto_login", False, autosave=False)
        self.config.save_config()
        
        # Stop screenshot capture
        self.screenshot_active = False
        
        # Stop monitoring
        if hasattr(self, 'input_listener'):
            self.input_listener.stop()
        
        if hasattr(self, 'idle_monitor'):
            self.idle_monitor.stop()
        
        # Safely check and stop thread
        if hasattr(self, 'thread') and self.thread is not None:
            if self.thread.is_alive():
                self.thread.join(0.5)  # Reduced timeout
        
        # Hide tray icon
        if hasattr(self, 'tray_icon') and self.tray_icon:
            self.tray_icon.hide()
        
        reset_global_variables()
        
        # Create and show login window
        self.login_window = LoginWindow(self.config)
        self.login_window.from_logout = True
        self.login_window.show()
        
        # Close current window
        self._force_close = True
        self.close()


    def _check_idle_recovery(self):
      """Check after delay if user really returned from idle"""
      with self.idle_monitor.lock:
          still_idle = (time.time() - self.idle_monitor.last_activity) >= self.idle_threshold

      if not still_idle:
          self.was_idle = False
          self._last_tray_state = False
          self.active_circle.setText("Running")
          self.active_circle.setStyleSheet("""
              background-color: #4CAF50; 
              color: white; 
              font-size: 20px; 
              border-radius: 75px;
          """)
          self.tray_icon.setIcon(QIcon(resource_path("icon.ico")))    

    def update_idle_state(self, idle_time):
        if not self.screenshot_active:
            return

        self.update_idle_display(idle_time)

        is_idle = idle_time >= self.idle_threshold

        # Always check if tray icon needs updating, even if state seems the same
        if is_idle != self.was_idle or getattr(self, "_last_tray_state", None) != is_idle:
            if not is_idle and self.was_idle:
                # ✅ Use QTimer instead of blocking sleep
                QTimer.singleShot(1000, self._check_idle_recovery)
                return

            # Save state
            self.was_idle = is_idle
            self._last_tray_state = is_idle  # Track last tray state separately

            mins, secs = divmod(int(idle_time), 60)
            self.idle_label.setText(f"Idle for: {mins:02}:{secs:02}")

            if is_idle:
                self.tray_icon.setIcon(QIcon(resource_path("yellow-icon.ico")))
                self.active_circle.setText("Idle")
                self.active_circle.setStyleSheet("""
                    background-color: #42A5F5; 
                    color: white; 
                    font-size: 20px; 
                    border-radius: 75px;
                """)
            else:
                self.tray_icon.setIcon(QIcon(resource_path("icon.ico")))
                self.active_circle.setText("Running")
                self.active_circle.setStyleSheet("""
                    background-color: #4CAF50; 
                    color: white; 
                    font-size: 20px; 
                    border-radius: 75px;
            """)
     # ================== NEW CLEANUP FUNCTION ==================
    def cleanup_old_screenshots(self, max_age_days=1):
        """Delete screenshots older than max_age_days (default = 1 day)"""
        folder = "screenshots"
        cutoff = time.time() - (max_age_days * 24 * 3600)  # 1 day in seconds

        try:
            for file in os.listdir(folder):
                file_path = os.path.join(folder, file)
                if not os.path.isfile(file_path):
                    continue
                if "idle.jpg" in file_path:  # keep static idle image
                    continue
                if os.path.getmtime(file_path) < cutoff:
                    os.remove(file_path)
                    #print(f"[CLEANUP] Deleted old screenshot: {file_path}")
        except Exception as e:
            print(f"[ERROR] Cleanup failed: {e}")
            #logger.error(f"[ERROR] Cleanup failed: {e}")
    # ===========================================================


    def screenshot_loop(self):
      try:
          os.makedirs("screenshots", exist_ok=True)
          target_size = (1280, 720)
          last_upload_time = 0
          idle_image_sent = False
          previous_idle = None  # Track if the previous loop was idle

          while self.screenshot_active and not self._shutting_down:
              try:
                  # === NEW: call cleanup function once per loop ===
                  self.cleanup_old_screenshots(max_age_days=1)

                  with self.idle_monitor.lock:
                      is_idle = (time.time() - self.idle_monitor.last_activity) >= self.idle_threshold

                  current_time = time.time()

                  # 1. IDLE MODE
                  if is_idle:
                      if not idle_image_sent or (current_time - last_upload_time) >= self.screenshot_interval:
                          idle_file = resource_path("idle.jpg")
                          success = send_screenshot(USER_ID, ORG_ID, file_path=idle_file, idle_status=0)
                          if not success:
                              print(f"[WARNING] Idle image upload failed, keeping file: {idle_file}")
                          idle_image_sent = True
                          last_upload_time = current_time

                  # 2. SWITCH: From IDLE → ACTIVE
                  elif previous_idle is True:
                      #print("[DEBUG] Switched from idle to active — capturing screenshot immediately")
                      timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
                      final_file = f"screenshots/{USER_ID}_{ORG_ID}_{timestamp}.jpg"

                      screenshot = pyautogui.screenshot()
                      screenshot = screenshot.resize(target_size)
                      # 🔑 Apply blur filter
                      screenshot = screenshot.filter(ImageFilter.GaussianBlur(radius=3))  # radius can be tuned
                      screenshot.save(final_file, "JPEG", optimize=True, quality=10)

                      success = send_screenshot(USER_ID, ORG_ID, file_path=final_file)

                      if success:
                          try:
                              if os.path.exists(final_file):
                                  os.remove(final_file)
                                  #print(f"[DEBUG] Deleted local screenshot: {final_file}")
                          except Exception as e:
                              print(f"[WARNING] Failed to delete screenshot: {e}")
                              #logger.error(f"[WARNING] Failed to delete screenshot: {e}")
                      else:
                          print(f"[WARNING] Keeping screenshot because upload failed: {final_file}")

                      last_upload_time = current_time
                      idle_image_sent = False

                  # 3. ACTIVE MODE: Every 5 minutes
                  elif (current_time - last_upload_time) >= 300:
                      timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
                      final_file = f"screenshots/{USER_ID}_{ORG_ID}_{timestamp}.jpg"

                      screenshot = pyautogui.screenshot()
                      screenshot = screenshot.resize(target_size)
                      # 🔑 Apply blur filter
                      screenshot = screenshot.filter(ImageFilter.GaussianBlur(radius=3))  # radius can be tuned
                      screenshot.save(final_file, "JPEG", optimize=True, quality=10)

                      success = send_screenshot(USER_ID, ORG_ID, file_path=final_file)

                      if success:
                          try:
                              if os.path.exists(final_file):
                                  os.remove(final_file)
                                  print(f"[DEBUG] Deleted local screenshot: {final_file}")
                          except Exception as e:
                              print(f"[WARNING] Failed to delete screenshot: {e}")
                              #logger.error(f"[WARNING] Failed to delete screenshot: {e}")
                      else:
                          print(f"[WARNING] Keeping screenshot because upload failed: {final_file}")

                      last_upload_time = current_time
                      idle_image_sent = False

                  previous_idle = is_idle
                  time.sleep(1)

              except Exception as e:
                  #logger.error(f"Screenshot error: {e}")
                  time.sleep(5)
      except Exception as e:
          #logging.exception("FATAL: Screenshot loop crashed")
          print("FATAL: Screenshot loop crashed")


    def reset_idle_timer(self, *args):
        try:
            current_time = time.time()
            if current_time - self.last_input_time >= 1:
                self.last_input_time = current_time
                if self.was_idle and self.screenshot_active:
                    # ✅ Use QTimer instead of blocking sleep
                    QTimer.singleShot(1000, self._check_idle_recovery)
        except Exception as e:
            print(f"Error in reset_idle_timer: {e}")
                
        def bring_to_front(self):
            self.show()
            self.setWindowState(self.windowState() & ~Qt.WindowMinimized | Qt.WindowActive)
            self.activateWindow()

            
class ConfigManager:
    def __init__(self):
        self.lock = threading.Lock()
        # Get appropriate config directory based on OS
        config_dir = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
        if not config_dir:
            config_dir = os.path.expanduser("~")
        
        # Create config directory if it doesn't exist
        self.config_dir = config_dir
        os.makedirs(self.config_dir, exist_ok=True)
        
        self.config_file = os.path.join(self.config_dir, "config.json")
        self._init_crypto()
        self.config = self._load_config()
        
        
    def _init_crypto(self):
        """Initialize encryption key"""
        key_path = os.path.join(self.config_dir, ".encryption_key")
        
        # Try to load existing key or generate new one
        try:
            if os.path.exists(key_path):
                with open(key_path, 'rb') as f:
                    self.crypto_key = f.read()
            else:
                self.crypto_key = Fernet.generate_key()
                with open(key_path, 'wb') as f:
                    f.write(self.crypto_key)
        except Exception as e:
            #print(f"Error initializing encryption: {e}")
            #logger.error(f"Error initializing encryption: {e}")
            self.crypto_key = None
    
    def _encrypt(self, data):
        """Encrypt data if crypto is available"""
        if not self.crypto_key or not data or Fernet is None:
            return data
            
        try:
            f = Fernet(self.crypto_key)
            return f.encrypt(data.encode()).decode()
        except Exception as e:
            #print(f"Encryption failed: {e}")
            #logger.error(f"Encryption failed: {e}")
            return data

    def _decrypt(self, data):
        """Decrypt data if crypto is available"""
        if not self.crypto_key or not data or Fernet is None:
            return data
            
        try:
            f = Fernet(self.crypto_key)
            return f.decrypt(data.encode()).decode()
        except Exception as e:
            #print(f"Decryption failed: {e}")
            #logger.error(f"Decryption failed: {e}")
            return data
        
    def _load_config(self):
        """Load configuration from file or return defaults"""
        defaults = {
            "api_url": "",
            "remember_credentials": True,
            "saved_email": "",
            "saved_password": "",  # This will be encrypted
            "auto_login": False,
            "window_geometry": None
        }
        
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    loaded = json.load(f)
                    
                    # Decrypt password if it exists
                    if "saved_password" in loaded and loaded["saved_password"]:
                        loaded["saved_password"] = self._decrypt(loaded["saved_password"])
                        #print("[DEBUG] Decrypted password:", loaded["saved_password"])
                    
                    return {**defaults, **loaded}
        except Exception as e:
            print(f"Error loading config: {e}")
            #logger.error(f"Error loading config: {e}")
        
        return defaults

    def save_config(self):
        with self.lock:
            """Save current configuration to file"""
            try:
                # Make a copy of config to encrypt password
                to_save = self.config.copy()
                if "saved_password" in to_save:
                    to_save["saved_password"] = self._encrypt(to_save["saved_password"])
            
                with open(self.config_file, 'w') as f:
                    json.dump(to_save, f, indent=4)
                    #print("[DEBUG] Config saved to:", self.config_file)
                    #print("[DEBUG] Saved contents:", to_save)
            except Exception as e:
                print(f"Error saving config: {e}")
                #logger.error(f"Error saving config: {e}")
    
    def get(self, key, default=None):
        with self.lock:
            return self.config.get(key, default)

    def set(self, key, value, autosave=True):
        with self.lock:
            self.config[key] = value
            if autosave:
                self.save_config()

#code to check if multiple instances are running
def is_another_instance_running(app_id="effortrak_instance"):
    """Check if another instance of the app is running."""
    socket = QLocalSocket()
    socket.connectToServer(app_id)
    is_running = socket.waitForConnected(100)
    socket.close()
    return is_running

def create_instance_server(app_id="effortrak_instance", on_message=None):
    server = QLocalServer()
    if not server.listen(app_id):
        QLocalServer.removeServer(app_id)
        if not server.listen(app_id):
            #print("Failed to listen on server.")
            return None

    if on_message:
        def handle_connection():
            socket = server.nextPendingConnection()
            if socket and socket.waitForReadyRead(100):
                try:
                    message = bytes(socket.readAll()).decode()
                    on_message(message)
                except Exception as e:
                    print(f"[Tray] Failed to read incoming message: {e}")
                    #logger.error(f"[Tray] Failed to read incoming message: {e}")
            socket.disconnectFromServer()

        server.newConnection.connect(handle_connection)

    return server

# === Handle incoming messages from second instance ===
def on_instance_message(message):
    if message == "show":
        try:
            for widget in QApplication.topLevelWidgets():
                if hasattr(widget, 'bring_to_front'):
                    widget.bring_to_front()
                    break
        except Exception as e:
            print(f"Error bringing to front: {e}")
            #logger.error(f"Error bringing to front: {e}")




if __name__ == "__main__":
    add_to_startup()
   
    if platform.system() == 'Windows' and not is_admin():
        run_as_admin()
        sys.exit(0)

    if is_another_instance_running():
        try:
            socket = QLocalSocket()
            socket.connectToServer("effortrak_instance")
            if socket.waitForConnected(100):
                socket.write(b"show")
                socket.flush()
                socket.waitForBytesWritten(100)
                socket.disconnectFromServer()
        except Exception as e:
            print(f"Could not send signal to main instance: {e}")
            #logger.error(f"Could not send signal to main instance: {e}")
        sys.exit(0)
        
    single_instance_server = create_instance_server("effortrak_instance", on_instance_message)
    if not single_instance_server:
        #print("Failed to start instance server.")
        sys.exit(0)

    QThreadPool.globalInstance().setMaxThreadCount(5)
    reset_global_variables()
    app = QApplication(sys.argv)


    # ========================= splashScreen Load and resize image =================================
    pixmap = QPixmap(resource_path("effortrak-welcom.jpg"))
    scaled_pixmap = pixmap.scaled(500, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    
    splash = QSplashScreen(scaled_pixmap, Qt.WindowStaysOnTopHint)
    splash.setWindowFlag(Qt.FramelessWindowHint)
    
    font = QFont("Arial", 8, QFont.Bold)
    splash.setFont(font)


    # Center splash
    screen_geometry = QDesktopWidget().screenGeometry()
    x = (screen_geometry.width() - splash.width()) // 2
    y = (screen_geometry.height() - splash.height()) // 2
    splash.move(x, y)
    
    # Show the splash
    splash.show()
    app.processEvents()
    
    # ---- Dynamic Text Example ----
    splash.showMessage("V1.0.5", Qt.AlignBottom | Qt.AlignHCenter, Qt.black)
    app.processEvents()
    time.sleep(3)
    
    
    # --------------------------------
    
    #========================================================================================


    app.setApplicationName("Effortrak")
    app.setApplicationDisplayName("Effortrak")
    app.setOrganizationName("Keyline DigiTech")

    config_manager = ConfigManager()
    #logger.info("Configuration loaded")

    saved_url = config_manager.get("api_url")
    auto_login = config_manager.get("auto_login", False)
    remember_creds = config_manager.get("remember_credentials", False)
    has_credentials = config_manager.get("saved_email") and config_manager.get("saved_password")

    if saved_url and auto_login and remember_creds and has_credentials:
        #logger.info("Attempting auto-login")
        API_BASE = saved_url.rstrip('/') + "/api/"
        login_window = LoginWindow(config_manager)
        login_window.show()
        splash.finish(login_window)
    else:
        #logger.info("Showing API URL window (no auto-login)")
        url_window = APIUrlWindow(config_manager)
        url_window.show()
        splash.finish(url_window)

    sys.exit(app.exec_())
