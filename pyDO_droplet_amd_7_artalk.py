import os
import random
import string
import time
import webbrowser
import base64
import socket
from pydo import Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
TOKEN = os.getenv('DIGITALOCEAN_TOKEN_CREATE', "your_digitalocean_api_token_here")
DOMAIN = os.getenv('DOMAIN', "example.com")
VPC_UUID = os.getenv('VPC_UUID', "yout_vpc_uuid")
PASSWORD = os.getenv('DROPLET_PASSWORD', "YourPassword1234!")

def generate_random_id(length=4):
    """Generate a random alphanumeric ID"""
    characters = string.ascii_lowercase + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

def encode_password(password):
    """Encode password to base64 for user_data"""
    password_b64 = base64.b64encode(password.encode()).decode()
    return password_b64

def create_droplet_config():
    """Create droplet configuration with random ID and password"""
    random_id = generate_random_id(4)
    
    # Create cloud-init user data to set the password
    user_data = f"""#cloud-config
chpasswd:
  list: |
    root:{PASSWORD}
  expire: False
ssh_pwauth: true
runcmd:
  - echo "root:{PASSWORD}" | chpasswd
  - sed -i 's/^#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config
  - sed -i 's/^#PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config
  - systemctl restart ssh
"""
    
    # Base configuration from your curl command
    config = {
        "name": f"ubuntu-s-1vcpu-1gb-amd-lon1-{random_id}",
        "region": "lon1",
        "size": "s-1vcpu-1gb-amd",
        "image": "ubuntu-24-04-x64",
        "vpc_uuid": VPC_UUID,
        "tags": ["python-sdk", "automated", "password-auth", "wine-subdomain"],
        "monitoring": True,
        "ipv6": False,
        "with_droplet_agent": True,
        "user_data": user_data
    }
    
    print(f"📝 Generated droplet name: {config['name']}")
    return config

def init_client():
    """Initialize the PyDo client"""
    if TOKEN == "your_digitalocean_api_token_here":
        print("❌ Please set your DigitalOcean API token!")
        print("📝 You can generate one at: https://cloud.digitalocean.com/account/api/tokens")
        print("📝 Or create a .env file with DIGITALOCEAN_TOKEN=your_token")
        return None
    
    return Client(token=TOKEN)

def wait_for_droplet_ip(client, droplet_id, max_attempts=30):
    """Wait for droplet to get an IP address"""
    print("\n⏳ Waiting for droplet IP address...")
    
    for attempt in range(max_attempts):
        try:
            response = client.droplets.get(droplet_id=droplet_id)
            
            if response and 'droplet' in response:
                droplet = response['droplet']
                
                # Check if droplet has networks
                if 'networks' in droplet and 'v4' in droplet['networks']:
                    for network in droplet['networks']['v4']:
                        if network['type'] == 'public':
                            ip_address = network['ip_address']
                            print(f"✅ Got IP address: {ip_address}")
                            return ip_address
                
                print(f"⏳ Attempt {attempt + 1}/{max_attempts}: No IP yet, waiting...")
                time.sleep(5)
        except Exception as e:
            print(f"⚠️ Error checking IP: {e}")
            time.sleep(5)
    
    print("❌ Failed to get droplet IP address after multiple attempts")
    return None

def wait_for_droplet_active(client, droplet_id, max_attempts=30):
    """Wait for droplet to become active"""
    print("\n⏳ Waiting for droplet to become active...")
    
    for attempt in range(max_attempts):
        try:
            response = client.droplets.get(droplet_id=droplet_id)
            
            if response and 'droplet' in response:
                status = response['droplet']['status']
                if status == 'active':
                    print("✅ Droplet is now active!")
                    return True
                else:
                    print(f"⏳ Attempt {attempt + 1}/{max_attempts}: Status: {status}")
                    time.sleep(5)
        except Exception as e:
            print(f"⚠️ Error checking status: {e}")
            time.sleep(5)
    
    print("❌ Droplet did not become active in time")
    return False

def setup_domain_records(client, domain, subdomain, ip_address):
    """Set up domain records for the droplet IP - specifically for subdomain"""
    full_subdomain = f"{subdomain}.{domain}"
    print(f"\n📝 Setting up domain record for {full_subdomain} -> {ip_address}")
    
    try:
        # Check if domain exists by trying to get it
        try:
            # domains.get returns the domain if it exists
            domain_response = client.domains.get(domain_name=domain)
            print(f"✅ Domain {domain} exists")
        except Exception as e:
            # Domain doesn't exist, create it
            print(f"➕ Domain {domain} not found, creating...")
            domain_config = {
                "name": domain,
                "ip_address": ip_address
            }
            client.domains.create(body=domain_config)
            print(f"✅ Domain {domain} created successfully!")
        
        # List existing records to find and delete any existing record with same subdomain
        try:
            records_response = client.domains.list_records(domain_name=domain)
            if records_response and 'domain_records' in records_response:
                for record in records_response['domain_records']:
                    if record['type'] == 'A' and record['name'] == subdomain:
                        print(f"🗑️ Removing existing {subdomain} record (ID: {record['id']})...")
                        client.domains.delete_record(domain_name=domain, record_id=record['id'])
        except Exception as e:
            print(f"⚠️ Note: {e}")
        
        # Create A record for the subdomain
        record_config = {
            "type": "A",
            "name": subdomain,
            "data": ip_address,
            "ttl": 1800
        }
        
        print(f"➕ Creating A record for {subdomain}.{domain} pointing to {ip_address}...")
        create_response = client.domains.create_record(domain_name=domain, body=record_config)
        
        if create_response and 'domain_record' in create_response:
            print(f"✅ A record for {subdomain} created successfully! (ID: {create_response['domain_record']['id']})")
            return True
        else:
            print(f"❌ Failed to create record: {create_response}")
            return False
        
    except Exception as e:
        print(f"❌ Domain setup error: {e}")
        return False

def list_domain_records(client):
    """List all records for the domain"""
    print(f"\n📋 Current DNS records for {DOMAIN}:")
    
    try:
        response = client.domains.list_records(domain_name=DOMAIN)
        
        if response and 'domain_records' in response:
            records = response['domain_records']
            if records:
                wine_record_found = False
                for record in records:
                    if record['type'] == 'A':
                        display_name = f"{record['name']}.{DOMAIN}" if record['name'] != '@' else DOMAIN
                        print(f"  • {record['type']} {display_name} -> {record.get('data', 'N/A')}")
                        if record['name'] == SUBDOMAIN:
                            wine_record_found = True
                
                if not wine_record_found:
                    print(f"  ⚠️  No A record found for {SUBDOMAIN}.{DOMAIN}")
            else:
                print("  No records found")
        else:
            print("  Could not fetch records")
    except Exception as e:
        print(f"  Could not fetch records: {e}")

def create_droplet(client):
    """Create a new droplet using PyDo"""
    try:
        droplet_config = create_droplet_config()
        
        # Create the droplet
        print("🚀 Creating droplet...")
        response = client.droplets.create(body=droplet_config)
        
        if response and 'droplet' in response:
            droplet = response['droplet']
            droplet_id = droplet['id']
            droplet_name = droplet['name']
            
            print(f"✅ Droplet created successfully!")
            print(f"🆔 Droplet ID: {droplet_id}")
            print(f"📛 Droplet Name: {droplet_name}")
            
            # Wait for droplet to get IP
            droplet_ip = wait_for_droplet_ip(client, droplet_id)
            
            if droplet_ip:
                print(f"🌐 Droplet IP: {droplet_ip}")
                print(f"🔐 SSH Access: ssh root@{droplet_ip} (password: {PASSWORD})")
                
                # Set up domain record for subdomain
                setup_domain_records(client, DOMAIN, SUBDOMAIN, droplet_ip)
            
            # Terminal URL
            terminal_url = f"https://cloud.digitalocean.com/droplets/{droplet_id}/terminal/ui/"
            print(f"🔗 Terminal URL: {terminal_url}")
            
            return droplet_id, droplet_ip, droplet_name
        else:
            print(f"❌ Error creating droplet: {response}")
            return None, None, None
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return None, None, None

def test_subdomain_resolution(ip_address):
    """Test if the subdomain resolves"""
    try:
        full_domain = f"{SUBDOMAIN}.{DOMAIN}"
        print(f"\n🔍 Testing DNS resolution for {full_domain}...")
        
        # Note: This might not work immediately due to DNS propagation
        resolved_ip = socket.gethostbyname(full_domain)
        if resolved_ip == ip_address:
            print(f"✅ DNS resolved correctly to {resolved_ip}")
        else:
            print(f"⚠️ DNS resolved to {resolved_ip} (different from droplet IP {ip_address})")
            print("   This is normal during DNS propagation (can take up to 30 minutes)")
    except Exception as e:
        print(f"⏳ DNS not yet resolvable (normal during propagation): {e}")

def verify_domain_setup(client):
    """Verify the domain and records are properly set up"""
    print("\n🔍 Verifying domain setup...")
    
    try:
        # Check if domain exists
        domain_response = client.domains.get(domain_name=DOMAIN)
        if domain_response and 'domain' in domain_response:
            print(f"✅ Domain {DOMAIN} is registered in your account")
        
        # List records
        records_response = client.domains.list_records(domain_name=DOMAIN)
        if records_response and 'domain_records' in records_response:
            records = records_response['domain_records']
            subdomain_records = [r for r in records if r['type'] == 'A' and r['name'] == SUBDOMAIN]
            
            if subdomain_records:
                for record in subdomain_records:
                    print(f"✅ {SUBDOMAIN}.{DOMAIN} -> {record['data']} (TTL: {record['ttl']})")
            else:
                print(f"❌ No A record found for {SUBDOMAIN}.{DOMAIN}")
    except Exception as e:
        print(f"⚠️ Verification error: {e}")

# Main execution
if __name__ == "__main__":
    print("🚀 DigitalOcean Droplet Creator with Custom Subdomain")
    print("=" * 60)
    print(f"🔐 Password: {PASSWORD}")
    
    # Initialize client first to check token
    client = init_client()
    if not client:
        exit(1)
    
    print("=" * 60)
    
    # Get domain (can also prompt if needed)
    domain_input = input(f"Enter your domain (default: {DOMAIN}): ").strip()
    DOMAIN = domain_input if domain_input else DOMAIN
    
    # Get subdomain from user
    print("")
    print("📝 Subdomain Configuration")
    print("-" * 30)
    default_subdomain = "wine"
    subdomain_input = input(f"Enter subdomain for your app (default: {default_subdomain}): ").strip()
    SUBDOMAIN = subdomain_input if subdomain_input else default_subdomain
    
    print(f"🌐 Will create A record: {SUBDOMAIN}.{DOMAIN}")
    print("⚠️  WARNING: Password authentication is less secure than SSH keys!")
    print("=" * 60)
    
    if client:
        print(f"🌐 Domain to configure: {DOMAIN}")
        
        # Check current DNS records
        list_domain_records(client)
        
        # Confirm before creating
        print("")
        confirm = input(f"Create droplet with subdomain {SUBDOMAIN}.{DOMAIN}? (y/n): ").lower()
        if confirm == 'n':
            print("👋 Cancelled.")
            exit(0)
        
        # Create single droplet
        droplet_id, droplet_ip, droplet_name = create_droplet(client)
        
        if droplet_id and droplet_ip:
            print(f"\n✅ Setup complete!")
            print(f"💻 Droplet Name: {droplet_name}")
            print(f"🆔 Droplet ID: {droplet_id}")
            print(f"🌐 IP Address: {droplet_ip}")
            print(f"🔐 SSH Command: ssh root@{droplet_ip}")
            print(f"🔐 Password: {PASSWORD}")
            print(f"🔗 Your subdomain: http://{SUBDOMAIN}.{DOMAIN}")
            print(f"🔗 Terminal: https://cloud.digitalocean.com/droplets/{droplet_id}/terminal/ui/")
            
            # Verify domain setup
            verify_domain_setup(client)
            
           
            # Optional: Wait for droplet to be active
            wait_option = input("\n⏰ Wait for droplet to become active? (Y/n): ").lower()
            if wait_option == '' or wait_option == 'y':
                wait_for_droplet_active(client, droplet_id)

            # Show final DNS records
            print("\n📋 Final DNS records:")
            list_domain_records(client)

            # Test the subdomain (optional)
            test_option = input("\n🔍 Test DNS resolution? (Y/n): ").lower()
            if test_option == '' or test_option == 'y':
                test_subdomain_resolution(droplet_ip)

            # Open terminal in browser
            open_browser = input("\n🌐 Open terminal in browser? (y/n): ").lower()
            if open_browser == '' or open_browser == 'y':
                webbrowser.open(f"https://cloud.digitalocean.com/droplets/{droplet_id}/terminal/ui/")
            
        
        print("\n✨ All done!")
        print(f"🌐 Your site will be available at: http://{SUBDOMAIN}.{DOMAIN}")
        print("⏱️  Note: DNS changes may take up to 30 minutes to propagate worldwide")
        print(f"🔐 Remember your password: {PASSWORD}")