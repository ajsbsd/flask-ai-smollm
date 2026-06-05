from werkzeug.security import generate_password_hash, check_password_hash

# Let's test the hash with the password with and without quotes, and see what happens
pw_clean = "j2hna;dhw3;8oi;sfaad"
pw_quotes = '"j2hna;dhw3;8oi;sfaad"'

# Let's see if we can check a simulated hash
db_hash = "scrypt:32768:8:1$so0zSMfUaMb18m82$ccc6168b707dc35fb80d9f31079d637f4dff4f24a8238d430ba8e6a8fc02f3e80eaf4d5d9bc9685cce58d8ec8e94681468c5d7ad9a71759162b0d47ce3538d4a"

print("Clean PW matches?", check_password_hash(db_hash, pw_clean))
print("Quotes PW matches?", check_password_hash(db_hash, pw_quotes))
