#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Скрипт для генерации самоподписанного SSL сертификата
"""

import os
import subprocess
import sys

def generate_self_signed_cert():
    """Генерирует самоподписанный SSL сертификат"""
    
    # Создаем директорию для сертификатов
    cert_dir = "ssl_certs"
    if not os.path.exists(cert_dir):
        os.makedirs(cert_dir)
    
    cert_file = os.path.join(cert_dir, "cert.pem")
    key_file = os.path.join(cert_dir, "key.pem")
    
    # Проверяем, есть ли уже сертификаты
    if os.path.exists(cert_file) and os.path.exists(key_file):
        print("✅ SSL сертификаты уже существуют")
        return cert_file, key_file
    
    try:
        # Генерируем приватный ключ
        subprocess.run([
            "openssl", "genrsa", "-out", key_file, "2048"
        ], check=True)
        
        # Генерируем сертификат
        subprocess.run([
            "openssl", "req", "-new", "-x509", "-key", key_file, 
            "-out", cert_file, "-days", "365", "-subj",
            "/C=RU/ST=Moscow/L=Moscow/O=TWAS Label/OU=IT/CN=193.104.57.60"
        ], check=True)
        
        print("✅ SSL сертификаты успешно созданы")
        print(f"   Сертификат: {cert_file}")
        print(f"   Ключ: {key_file}")
        
        return cert_file, key_file
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка при создании SSL сертификата: {e}")
        return None, None
    except FileNotFoundError:
        print("❌ OpenSSL не найден. Установите OpenSSL или используйте готовые сертификаты")
        return None, None

if __name__ == "__main__":
    cert_file, key_file = generate_self_signed_cert()
    if cert_file and key_file:
        print(f"\n🔐 SSL сертификаты готовы:")
        print(f"   Сертификат: {cert_file}")
        print(f"   Приватный ключ: {key_file}")
        print(f"\n📝 Для использования в production рекомендуется получить сертификат от Let's Encrypt")
    else:
        print("\n❌ Не удалось создать SSL сертификаты")
        sys.exit(1)

