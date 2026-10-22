import secrets

def generate_otp():
    # secrets, not random: OTPs must be unpredictable
    return str(secrets.randbelow(900000) + 100000)
