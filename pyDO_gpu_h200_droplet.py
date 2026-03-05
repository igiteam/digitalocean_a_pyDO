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

# GPU Droplet size - using GPU-optimized droplet (H100)
GPU_SIZE = "gpu-h100x1-80gb"  # 1x H100 GPU, 80GB VRAM
CPU_SIZE = "s-1vcpu-1gb-amd"   # Fallback CPU size

def generate_random_id(length=4):
    """Generate a random alphanumeric ID"""
    characters = string.ascii_lowercase + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

def encode_password(password):
    """Encode password to base64 for user_data"""
    password_b64 = base64.b64encode(password.encode()).decode()
    return password_b64

def create_droplet_config(use_gpu=False):
    """Create droplet configuration with random ID and password"""
    random_id = generate_random_id(4)
    
    # Select size based on GPU flag
    if use_gpu:
        size = GPU_SIZE
        droplet_type = "gpu"
    else:
        size = CPU_SIZE
        droplet_type = "cpu"
    
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
  - mkdir -p /opt/forgejo
  - mkdir -p /opt/git/data
  - mkdir -p /var/www/uploads
  - chmod 777 /var/www/uploads
"""
    
    # Base configuration
    config = {
        "name": f"ubuntu-{droplet_type}-{size}-lon1-{random_id}",
        "region": "lon1",
        "size": size,
        "image": "ubuntu-24-04-x64",
        "vpc_uuid": VPC_UUID,
        "tags": ["python-sdk", "automated", "password-auth", "main-domain", "all-subdomains"],
        "monitoring": True,
        "ipv6": False,
        "with_droplet_agent": True,
        "user_data": user_data
    }
    
    print(f"📝 Generated droplet name: {config['name']}")
    print(f"💻 Droplet size: {size}")
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
    """Set up ALL domain records for the droplet IP"""
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
        
        # Define ALL records to create
        all_records = [
            # Root domain (@)
            {"type": "A", "name": "@", "data": ip_address, "ttl": 1800},
            
            # WWW subdomain
            {"type": "A", "name": "www", "data": ip_address, "ttl": 1800},
        ]
        
        # Add all subdomains from the list
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
                # Group by type for better display
                a_records = []
                cname_records = []
                other_records = []
                
                for record in records:
                    if record['type'] == 'A':
                        a_records.append(record)
                    elif record['type'] == 'CNAME':
                        cname_records.append(record)
                    else:
                        other_records.append(record)
                
                if a_records:
                    print("\n  A Records:")
                    for record in sorted(a_records, key=lambda x: x['name']):
                        display_name = f"{record['name']}.{domain}" if record['name'] != '@' else domain
                        print(f"    • {display_name:30} -> {record.get('data', 'N/A')} (TTL: {record.get('ttl', 'N/A')})")
                
                if cname_records:
                    print("\n  CNAME Records:")
                    for record in sorted(cname_records, key=lambda x: x['name']):
                        display_name = f"{record['name']}.{domain}"
                        print(f"    • {display_name:30} -> {record.get('data', 'N/A')}")
                
                if other_records:
                    print("\n  Other Records:")
                    for record in other_records:
                        print(f"    • {record['type']} {record['name']} -> {record.get('data', 'N/A')}")
            else:
                print("  No records found")
        else:
            print("  Could not fetch records")
    except Exception as e:
        print(f"  Could not fetch records: {e}")

def create_droplet(client, use_gpu=False):
    """Create a new droplet using PyDo"""
    try:
        droplet_config = create_droplet_config(use_gpu)
        
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
    
    all_domains = [domain] + [f"{sub}.{domain}" for sub in subdomains if sub != '@']
    
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
            
            # Delete any existing A records for our subdomains
            for record in records:
                if record['type'] == 'A' and record['name'] in subdomains:
                    print(f"  Removing existing {record['name']}.{domain} record...")
                    try:
                        client.domains.delete_record(domain_name=domain, record_id=record['id'])
                    except:
                        pass
    except:
        pass

# Main execution
if __name__ == "__main__":
    print("🚀 DigitalOcean GPU Droplet Creator")
    print("=" * 70)
    print(f"🔐 Password: {PASSWORD}")
    
    # Initialize client first to check token
    client = init_client()
    if not client:
        exit(1)
    
    print("=" * 70)
    
    # Get domain (can also prompt if needed)
    domain_input = input(f"Enter your domain (default: {DOMAIN}): ").strip()
    DOMAIN = domain_input if domain_input else DOMAIN
    
    # Define ONLY the subdomains you explicitly asked for
    DEFAULT_SUBDOMAINS = [
        "@",           # Root domain
        "www",         # WWW
        "vscode",      # VS Code in browser
        "rag",         # Vector DB API
        "searxng",     # Private search
        "files",       # FileServer (HTML, .codecanvas, .diff)
        "upload",      # 📤 DumbDrop upload portal
        "debugger",    # Taguchi dashboard
        "codecanvas",  # Project visualizer
        "dagu",        # CRON jobs / Workflow engine
        "bytestash",   # Codasnippet sharing
        "multibash",   # Multibash generator
        "dashboard",   # Dashboard CRON jobs
        "gitgpt",      # Main chat
        "api",         # API endpoint
        "auth",        # Authentication
        "terminal",    # xterm.js web terminal
        "forgejo",     # Forgejo Git service
        "wine",        # WINEJS (Windows apps)
    ]
    
    print("\n📝 Subdomains Configuration")
    print("-" * 40)
    print(f"Will create A records for:")
    for sub in DEFAULT_SUBDOMAINS:
        if sub == '@':
            print(f"  • {DOMAIN} (root domain)")
        else:
            print(f"  • {sub}.{DOMAIN}")
    
    print("\n⚠️  WARNING: Password authentication is less secure than SSH keys!")
    print("=" * 70)
    
    if client:
        print(f"🌐 Domain to configure: {DOMAIN}")
        
        # Show current DNS records
        list_domain_records(client, DOMAIN)
        
        # Ask about GPU droplet
        print("\n💻 Droplet Type Selection")
        print("-" * 40)
        print("1) GPU Droplet (H100, 80GB VRAM) - $2-3/hr")
        print("2) CPU Droplet ($6/month) - for testing")
        
        gpu_choice = input("Select droplet type (1/2) [default: 2]: ").strip()
        use_gpu = (gpu_choice == "1")
        
        if use_gpu:
            print("\n⚠️  WARNING: GPU droplets are expensive ($2-3 per hour)!")
            confirm_gpu = input("Are you sure you want a GPU droplet? (y/N): ").lower()
            if confirm_gpu != 'y':
                use_gpu = False
                print("Using CPU droplet instead.")
        
        # Confirm before creating
        print("")
        confirm = input(f"Create {'GPU' if use_gpu else 'CPU'} droplet with ALL {len(DEFAULT_SUBDOMAINS)} subdomains? (y/n): ").lower()
        if confirm == 'n':
            print("👋 Cancelled.")
            exit(0)
        
        # Delete existing records to avoid conflicts
        delete_existing_records(client, DOMAIN, DEFAULT_SUBDOMAINS)
        
        # Create droplet
        droplet_id, droplet_ip, droplet_name = create_droplet(client, use_gpu)
        
        if droplet_id and droplet_ip:
            print(f"\n✅ Droplet created!")
            print(f"💻 Droplet Name: {droplet_name}")
            print(f"🆔 Droplet ID: {droplet_id}")
            print(f"🌐 IP Address: {droplet_ip}")
            print(f"🔐 SSH Command: ssh root@{droplet_ip}")
            print(f"🔐 Password: {PASSWORD}")
            
            # Set up ALL domain records
            setup_domain_records(client, DOMAIN, droplet_ip, DEFAULT_SUBDOMAINS)
            
            print(f"\n🌐 Your domains:")
            print(f"  • https://{DOMAIN}                         # Main site")
            print(f"  • https://www.{DOMAIN}                     # WWW")
            print(f"  • https://vscode.{DOMAIN}                  # VS Code in browser")
            print(f"  • https://rag.{DOMAIN}                     # Vector DB API")
            print(f"  • https://searxng.{DOMAIN}                 # Private search")
            print(f"  • https://files.{DOMAIN}                   # FileServer")
            print(f"  • https://upload.{DOMAIN}                  # 📤 DumbDrop upload")
            print(f"  • https://debugger.{DOMAIN}                # Taguchi dashboard")
            print(f"  • https://codecanvas.{DOMAIN}              # Project visualizer")
            print(f"  • https://dagu.{DOMAIN}                    # CRON jobs")
            print(f"  • https://bytestash.{DOMAIN}               # Codasnippet sharing")
            print(f"  • https://multibash.{DOMAIN}               # Multibash generator")
            print(f"  • https://dashboard.{DOMAIN}               # Dashboard")
            print(f"  • https://gitgpt.{DOMAIN}                  # Main chat")
            print(f"  • https://api.{DOMAIN}                     # API endpoint")
            print(f"  • https://auth.{DOMAIN}                    # Authentication")
            print(f"  • https://terminal.{DOMAIN}                # xterm.js terminal")
            print(f"  • https://forgejo.{DOMAIN}                 # Forgejo Git service")
            print(f"  • https://wine.{DOMAIN}                    # WINEJS")

            print(f"🔗 Terminal: https://cloud.digitalocean.com/droplets/{droplet_id}/terminal/ui/")
            
            # Verify domain setup
            verify_domain_setup(client, DOMAIN, DEFAULT_SUBDOMAINS)
            
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
                test_domain_resolution(DOMAIN, DEFAULT_SUBDOMAINS, droplet_ip)

            # Open terminal in browser
            open_browser = input("\n🌐 Open terminal in browser? (y/n): ").lower()
            if open_browser == '' or open_browser == 'y':
                webbrowser.open(f"https://cloud.digitalocean.com/droplets/{droplet_id}/terminal/ui/")
        
        print("\n✨ All done!")
        print(f"🌐 Your platform is ready at:")
        print(f"  • https://{DOMAIN}")
        print(f"  • https://vscode.{DOMAIN}")
        print(f"  • https://rag.{DOMAIN}")
        print(f"  • https://searxng.{DOMAIN}")
        print(f"  • https://files.{DOMAIN}")
        print(f"  • https://upload.{DOMAIN}")
        print(f"  • https://debugger.{DOMAIN}")
        print(f"  • https://codecanvas.{DOMAIN}")
        print(f"  • https://dagu.{DOMAIN}")
        print(f"  • https://bytestash.{DOMAIN}")
        print(f"  • https://multibash.{DOMAIN}")
        print(f"  • https://dashboard.{DOMAIN}")
        print(f"  • https://gitgpt.{DOMAIN}")
        print(f"  • https://api.{DOMAIN}")
        print(f"  • https://auth.{DOMAIN}")
        print(f"  • https://terminal.{DOMAIN}")
        print(f"  • https://forgejo.{DOMAIN}")
        print(f"  • https://wine.{DOMAIN}")
        print("⏱️  Note: DNS changes may take up to 30 minutes to propagate worldwide")
        print(f"🔐 Remember your password: {PASSWORD}")