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
DOMAIN = os.getenv('DOMAIN', "sdappnet.cloud")
VPC_UUID = os.getenv('VPC_UUID', "d7ad8c4c-6258-4656-82a5-51af9523f641")
PASSWORD = os.getenv('DROPLET_PASSWORD', "FuckYou11!!a")

# CPU Droplet size
CPU_SIZE = "s-1vcpu-1gb-amd"   # $6/month droplet

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
package_update: true
packages:
  - curl
  - wget
  - git
  - build-essential
  - nginx
  - certbot
  - python3-certbot-nginx
  - docker.io
  - docker-compose
  - python3-pip
  - nodejs
  - npm
  - tmux
  - screen
runcmd:
  - echo "root:{PASSWORD}" | chpasswd
  - sed -i 's/^#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config
  - sed -i 's/^#PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config
  - systemctl restart ssh
  - systemctl enable docker
  - systemctl start docker
  - curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  - apt-get install -y nodejs
  - npm install -g pm2
  - mkdir -p /var/www/uploads
  - chmod 777 /var/www/uploads
"""
    
    # Base configuration
    config = {
        "name": f"ubuntu-{CPU_SIZE}-lon1-{random_id}",
        "region": "lon1",
        "size": CPU_SIZE,
        "image": "ubuntu-24-04-x64",
        "vpc_uuid": VPC_UUID,
        "tags": ["python-sdk", "automated", "password-auth", "main-domain"],
        "monitoring": True,
        "ipv6": False,
        "with_droplet_agent": True,
        "user_data": user_data
    }
    
    print(f"📝 Generated droplet name: {config['name']}")
    print(f"💻 Droplet size: {CPU_SIZE} ($6/month)")
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

def setup_domain_records(client, domain, ip_address, subdomains):
    """Set up domain records for the droplet IP"""
    print(f"\n📝 Setting up domain records for {domain} -> {ip_address}")
    
    try:
        # Check if domain exists
        try:
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
        
        # First, list all existing records to avoid duplicates
        existing_records = {}
        try:
            records_response = client.domains.list_records(domain_name=domain)
            if records_response and 'domain_records' in records_response:
                for record in records_response['domain_records']:
                    key = f"{record['type']}_{record['name']}"
                    existing_records[key] = record
        except Exception as e:
            print(f"⚠️ Could not list existing records: {e}")
        
        # Define records to create (just the 4 you want)
        all_records = [
            # Root domain (@) - this is gitgpt.com
            {"type": "A", "name": "@", "data": ip_address, "ttl": 1800},
        ]
        
        # Add the 3 subdomains you want
        for subdomain in subdomains:
            all_records.append({
                "type": "A",
                "name": subdomain,
                "data": ip_address,
                "ttl": 1800
            })
        
        # Create each record
        for record_config in all_records:
            record_key = f"{record_config['type']}_{record_config['name']}"
            
            # Check if record already exists
            if record_key in existing_records:
                existing = existing_records[record_key]
                if existing['data'] != record_config['data']:
                    print(f"🔄 Updating {record_config['name']}.{domain} from {existing['data']} to {record_config['data']}...")
                    client.domains.update_record(
                        domain_name=domain,
                        record_id=existing['id'],
                        body=record_config
                    )
                else:
                    print(f"✅ {record_config['name']}.{domain} already points to {record_config['data']}")
            else:
                # Create new record
                display_name = record_config['name'] if record_config['name'] != '@' else domain
                print(f"➕ Creating A record for {display_name} -> {record_config['data']}...")
                try:
                    create_response = client.domains.create_record(domain_name=domain, body=record_config)
                    if create_response and 'domain_record' in create_response:
                        print(f"✅ Created: {display_name}")
                except Exception as e:
                    print(f"⚠️ Could not create {display_name}: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ Domain setup error: {e}")
        return False

def list_domain_records(client, domain):
    """List all records for the domain"""
    print(f"\n📋 Current DNS records for {domain}:")
    
    try:
        response = client.domains.list_records(domain_name=domain)
        
        if response and 'domain_records' in response:
            records = response['domain_records']
            if records:
                a_records = [r for r in records if r['type'] == 'A']
                
                if a_records:
                    print("\n  A Records:")
                    for record in sorted(a_records, key=lambda x: x['name']):
                        display_name = f"{record['name']}.{domain}" if record['name'] != '@' else domain
                        print(f"    • {display_name:30} -> {record.get('data', 'N/A')} (TTL: {record.get('ttl', 'N/A')})")
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

def test_domain_resolution(domain, subdomains, ip_address):
    """Test if domains resolve to the correct IP"""
    print(f"\n🔍 Testing DNS resolution...")
    
    all_domains = [domain] + [f"{sub}.{domain}" for sub in subdomains]
    
    for test_domain in all_domains:
        try:
            resolved_ip = socket.gethostbyname(test_domain)
            if resolved_ip == ip_address:
                print(f"✅ {test_domain:30} -> {resolved_ip} (correct)")
            else:
                print(f"⚠️ {test_domain:30} -> {resolved_ip} (expected {ip_address})")
                print("   This is normal during DNS propagation (can take up to 30 minutes)")
        except Exception as e:
            print(f"⏳ {test_domain:30} not yet resolvable: {e}")

def verify_domain_setup(client, domain, subdomains):
    """Verify the domain and records are properly set up"""
    print("\n🔍 Verifying domain setup...")
    
    try:
        # Check if domain exists
        domain_response = client.domains.get(domain_name=domain)
        if domain_response and 'domain' in domain_response:
            print(f"✅ Domain {domain} is registered in your account")
        
        # List all records
        records_response = client.domains.list_records(domain_name=domain)
        if records_response and 'domain_records' in records_response:
            records = records_response['domain_records']
            
            # Check for A records
            a_records = [r for r in records if r['type'] == 'A']
            
            print(f"\n  Found {len(a_records)} A records:")
            for record in a_records:
                display_name = f"{record['name']}.{domain}" if record['name'] != '@' else domain
                print(f"    • {display_name:30} -> {record['data']}")
            
            # Check for missing subdomains
            existing_names = [r['name'] for r in a_records]
            missing = []
            
            for sub in subdomains:
                if sub not in existing_names:
                    missing.append(sub)
            
            if missing:
                print(f"\n  ⚠️  Missing records: {', '.join(missing)}.{domain}")
    except Exception as e:
        print(f"⚠️ Verification error: {e}")

def delete_existing_records(client, domain, subdomains):
    """Delete existing A records for subdomains to avoid conflicts"""
    print("\n🗑️ Checking for existing records to avoid conflicts...")
    
    try:
        records_response = client.domains.list_records(domain_name=domain)
        if records_response and 'domain_records' in records_response:
            records = records_response['domain_records']
            
            # Delete any existing A records for our subdomains (including @)
            for record in records:
                if record['type'] == 'A' and (record['name'] in subdomains or record['name'] == '@'):
                    print(f"  Removing existing {record['name']}.{domain} record...")
                    try:
                        client.domains.delete_record(domain_name=domain, record_id=record['id'])
                    except:
                        pass
    except:
        pass

# Main execution
if __name__ == "__main__":
    print("🚀 DigitalOcean Droplet Creator ($6/month CPU)")
    print("=" * 70)
    print(f"🔐 Password: {PASSWORD}")
    
    # Initialize client first to check token
    client = init_client()
    if not client:
        exit(1)
    
    print("=" * 70")
    
    # Get domain (can also prompt if needed)
    domain_input = input(f"Enter your domain (default: {DOMAIN}): ").strip()
    DOMAIN = domain_input if domain_input else DOMAIN
    
    # Define ONLY the 3 subdomains you want (plus root @ which is handled separately)
    SUBDOMAINS = [
        "vscode",      # VS Code in browser
        "rag",         # Vector DB API
        "bytestash",   # Codasnippet sharing
    ]
    
    print("\n📝 Domain Configuration")
    print("-" * 40)
    print(f"Will create A records for:")
    print(f"  • {DOMAIN} (root domain - gitgpt.com)")
    for sub in SUBDOMAINS:
        print(f"  • {sub}.{DOMAIN}")
    
    print("\n⚠️  WARNING: Password authentication is less secure than SSH keys!")
    print("=" * 70)
    
    if client:
        print(f"🌐 Domain to configure: {DOMAIN}")
        
        # Show current DNS records
        list_domain_records(client, DOMAIN)
        
        # Confirm before creating
        print("")
        confirm = input(f"Create CPU droplet ($6/month) with these {len(SUBDOMAINS)+1} domains? (y/n): ").lower()
        if confirm == 'n':
            print("👋 Cancelled.")
            exit(0)
        
        # Delete existing records to avoid conflicts
        delete_existing_records(client, DOMAIN, SUBDOMAINS)
        
        # Create droplet
        droplet_id, droplet_ip, droplet_name = create_droplet(client)
        
        if droplet_id and droplet_ip:
            print(f"\n✅ Droplet created!")
            print(f"💻 Droplet Name: {droplet_name}")
            print(f"🆔 Droplet ID: {droplet_id}")
            print(f"🌐 IP Address: {droplet_ip}")
            print(f"🔐 SSH Command: ssh root@{droplet_ip}")
            print(f"🔐 Password: {PASSWORD}")
            
            # Set up domain records (root @ + the 3 subdomains)
            setup_domain_records(client, DOMAIN, droplet_ip, SUBDOMAINS)
            
            print(f"\n🌐 Your domains:")
            print(f"  • https://{DOMAIN}                         # gitgpt.com (root)")
            print(f"  • https://vscode.{DOMAIN}                  # VS Code in browser")
            print(f"  • https://rag.{DOMAIN}                     # Vector DB API")
            print(f"  • https://bytestash.{DOMAIN}               # Codasnippet sharing")
            
            print(f"🔗 Terminal: https://cloud.digitalocean.com/droplets/{droplet_id}/terminal/ui/")
            
            # Verify domain setup
            verify_domain_setup(client, DOMAIN, SUBDOMAINS)
            
            # Show final DNS records
            print("\n📋 Final DNS records:")
            list_domain_records(client, DOMAIN)
            
            # Wait for droplet to be active
            wait_option = input("\n⏰ Wait for droplet to become active? (Y/n): ").lower()
            if wait_option == '' or wait_option == 'y':
                wait_for_droplet_active(client, droplet_id)

            # Test DNS resolution (optional)
            test_option = input("\n🔍 Test DNS resolution? (Y/n): ").lower()
            if test_option == '' or test_option == 'y':
                test_domain_resolution(DOMAIN, SUBDOMAINS, droplet_ip)

            # Open terminal in browser
            open_browser = input("\n🌐 Open terminal in browser? (y/n): ").lower()
            if open_browser == '' or open_browser == 'y':
                webbrowser.open(f"https://cloud.digitalocean.com/droplets/{droplet_id}/terminal/ui/")
        
        print("\n✨ All done!")
        print(f"🌐 Your platform is ready at:")
        print(f"  • https://{DOMAIN}                         # gitgpt.com (root)")
        print(f"  • https://vscode.{DOMAIN}                  # VS Code in browser")
        print(f"  • https://rag.{DOMAIN}                     # Vector DB API")
        print(f"  • https://bytestash.{DOMAIN}               # Codasnippet sharing")
        print("⏱️  Note: DNS changes may take up to 30 minutes to propagate worldwide")
        print(f"🔐 Remember your password: {PASSWORD}")