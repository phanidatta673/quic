import subprocess
import sys

def generate_cert():
    """Generate self-signed certificate for testing"""
    try:
        # Generate private key
        subprocess.run([
            'openssl', 'genrsa', '-out', 'key.pem', '2048'
        ], check=True)

        # Generate certificate
        subprocess.run([
            'openssl', 'req', '-new', '-x509', '-key', 'key.pem', 
            '-out', 'cert.pem', '-days', '365', '-subj', 
            '/C=US/ST=State/L=City/O=Organization/CN=localhost'
        ], check=True)

        print(" SSL certificates generated successfully!")
        print("Files created: cert.pem, key.pem")

    except subprocess.CalledProcessError as e:
        print(f"Error generating certificates: {e}")
        print("Make sure openssl is installed on your system")
        sys.exit(1)
    
if __name__ == '__main__':
    generate_cert()