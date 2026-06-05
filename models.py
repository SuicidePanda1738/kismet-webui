from app import db
from datetime import datetime
from sqlalchemy import JSON
from sqlalchemy.types import TypeDecorator, String
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from crypto_utils import encrypt_value, decrypt_value


class EncryptedString(TypeDecorator):
    """A String column whose value is transparently encrypted at rest.

    Plaintext is encrypted on write and decrypted on read, so application code
    keeps using the attribute as an ordinary string. Legacy plaintext rows are
    returned unchanged and re-encrypted the next time they are written.
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return encrypt_value(value)

    def process_result_value(self, value, dialect):
        return decrypt_value(value)

class KismetConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    config_name = db.Column(db.String(100), nullable=False, default='default')
    data_sources = db.Column(JSON, nullable=False, default=list)
    gps_config = db.Column(JSON, nullable=True)
    logging_config = db.Column(JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

class PushService(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    service_type = db.Column(db.String(20), nullable=False)  # 'WiFi' or 'Bluetooth'
    adapter = db.Column(db.String(50), nullable=False)
    sensor = db.Column(db.String(100), nullable=False)
    kismet_ip = db.Column(db.String(45), nullable=False)
    api_key = db.Column(EncryptedString(512), nullable=False)
    gps_api_key = db.Column(EncryptedString(512), nullable=True)
    status = db.Column(db.String(20), default='inactive')
    enabled = db.Column(db.Boolean, default=True, nullable=False)  # auto-start on boot
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
