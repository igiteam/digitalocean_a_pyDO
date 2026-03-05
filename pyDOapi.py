import os
import random
import string
import time
import base64
import json
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import boto3
from jinja2 import Environment, FileSystemLoader
from pydo import Client
from dotenv import load_dotenv
import uvicorn
import secrets

load_dotenv()

# Configuration
DO_TOKEN = os.getenv('DIGITALOCEAN_TOKEN')
SPACES_KEY = os.getenv('SPACES_KEY')
SPACES_SECRET = os.getenv('SPACES_SECRET')
SPACES_REGION = os.getenv('SPACES_REGION', 'lon1')
SPACES_BUCKET = os.getenv('SPACES_BUCKET', 'winejs-installers')
DOMAIN = os.getenv('DOMAIN', 'sdappnet.cloud')
VPC_UUID = os.getenv('VPC_UUID', 'd7ad8c4c-6258-4656-82a5-51af9523f641')

app = FastAPI(title="WINEJS Deployment API", version="1.0.0")

# Initialize clients
do_client = Client(token=DO_TOKEN)

# Setup Jinja2 template environment
template_env = Environment(loader=FileSystemLoader('templates'))

# Initialize Spaces client (S3-compatible)
spaces_client = boto3.client(
    's3',
    region_name=SPACES_REGION,
    endpoint_url=f'https://{SPACES_REGION}.digitaloceanspaces.com',
    aws_access_key_id=SPACES_KEY,
    aws_secret_access_key=SPACES_SECRET
)

class DeploymentRequest(BaseModel):
    """API request model for WINEJS deployment"""
    subdomain: str = Field("wine", description="Subdomain for the app")
    domain: Optional[str] = Field(DOMAIN, description="Main domain")
    droplet_size: str = Field("s-1vcpu-1gb-amd", description="Droplet size slug")
    region: str = Field("lon1", description="Region")
    root_password: Optional[str] = Field(None, description="Root password (auto-generated if not provided)")
    fileserver_password: Optional[str] = Field(None, description="FileServer password (auto-generated if not provided)")
    dumbdrop_pin: Optional[str] = Field(None, description="DumbDrop PIN (auto-generated if not provided)")
    email: str = Field("admin@sdappnet.cloud", description="SSL email")
    webhook_url: Optional[str] = Field(None, description="Webhook to notify when ready")
    
    class Config:
        schema_extra = {
            "example": {
                "subdomain": "games",
                "droplet_size": "s-2vcpu-4gb-amd",
                "region": "nyc1",
                "email": "admin@example.com"
            }
        }

class DeploymentResponse(BaseModel):
    """API response model"""
    deployment_id: str
    droplet_id: int
    droplet_ip: str
    subdomain: str
    domain: str
    url: str
    upload_url: str
    download_url: str
    installer_url: str
    root_password: str
    fileserver_password: str
    dumbdrop_pin: str
    milkshape_vnc_pass: str
    status: str

def generate_random_id(length=8):
    """Generate random ID for deployment"""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def generate_password(length=12):
    """Generate random password"""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def generate_pin():
    """Generate 6-digit PIN"""
    return ''.join(secrets.choice(string.digits) for _ in range(6))

def render_winejs_script(config: Dict[str, Any]) -> str:
    """Render the WINEJS setup script from template"""
    template = template_env.get_template('setup.sh.j2')
    return template.render(**config)

def upload_to_spaces(content: str, filename: str) -> str:
    """Upload script to DigitalOcean Spaces and return private URL"""
    try:
        # Upload with private ACL
        spaces_client.put_object(
            Bucket=SPACES_BUCKET,
            Key=filename,
            Body=content.encode('utf-8'),
            ContentType='text/x-shellscript',
            ACL='private'
        )
        
        # Generate presigned URL (valid for 1 hour)
        url = spaces_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': SPACES_BUCKET, 'Key': filename},
            ExpiresIn=3600  # 1 hour
        )
        return url
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Spaces upload failed: {e}")

def create_cloudinit_userdata(installer_url: str, root_password: str) -> str:
    """Generate cloud-init user-data that auto-installs WINEJS"""
    return f"""#cloud-config
chpasswd:
  list: |
    root:{root_password}
  expire: False
ssh_pwauth: true

# Auto-run the installer on first boot
runcmd:
  - [curl, -s, -o, /tmp/winejs.sh, "{installer_url}"]
  - [chmod, +x, /tmp/winejs.sh]
  - [bash, /tmp/winejs.sh]
  - [touch, /root/.winejs-installed]

# Save the config for reference
write_files:
  - path: /root/winejs-config.json
    content: |
      {{
        "installed_at": "$(date -Iseconds)",
        "installer_url": "{installer_url}"
      }}
    permissions: '0644'

final_message: "WINEJS installation started! Check /var/log/cloud-init-output.log for progress"
"""

def create_droplet_with_cloudinit(config: Dict[str, Any], user_data: str) -> Dict[str, Any]:
    """Create droplet with cloud-init user-data"""
    try:
        droplet_config = {
            "name": f"winejs-{config['deployment_id']}",
            "region": config['region'],
            "size": config['droplet_size'],
            "image": "ubuntu-24-04-x64",
            "vpc_uuid": VPC_UUID,
            "tags": ["winejs", "automated", config['subdomain']],
            "monitoring": True,
            "ipv6": False,
            "with_droplet_agent": True,
            "user_data": user_data
        }
        
        response = do_client.droplets.create(body=droplet_config)
        
        if response and 'droplet' in response:
            droplet = response['droplet']
            return {
                'id': droplet['id'],
                'name': droplet['name']
            }
        else:
            raise Exception("Failed to create droplet")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Droplet creation failed: {e}")

def wait_for_droplet_ip(droplet_id: int) -> str:
    """Wait for droplet to get an IP"""
    max_attempts = 30
    for attempt in range(max_attempts):
        try:
            response = do_client.droplets.get(droplet_id=droplet_id)
            if response and 'droplet' in response:
                droplet = response['droplet']
                for network in droplet['networks']['v4']:
                    if network['type'] == 'public':
                        return network['ip_address']
            time.sleep(5)
        except:
            time.sleep(5)
    
    raise HTTPException(status_code=500, detail="Timeout waiting for droplet IP")

def setup_dns(subdomain: str, domain: str, ip_address: str):
    """Create DNS record"""
    try:
        # Check if domain exists
        try:
            do_client.domains.get(domain_name=domain)
        except:
            do_client.domains.create(body={"name": domain, "ip_address": ip_address})
        
        # Remove existing record if any
        try:
            records = do_client.domains.list_records(domain_name=domain)
            if records and 'domain_records' in records:
                for record in records['domain_records']:
                    if record['type'] == 'A' and record['name'] == subdomain:
                        do_client.domains.delete_record(
                            domain_name=domain, 
                            record_id=record['id']
                        )
        except:
            pass
        
        # Create new record
        record_config = {
            "type": "A",
            "name": subdomain,
            "data": ip_address,
            "ttl": 1800
        }
        do_client.domains.create_record(domain_name=domain, body=record_config)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DNS setup failed: {e}")

@app.post("/deploy", response_model=DeploymentResponse)
async def deploy_winejs(request: DeploymentRequest, background_tasks: BackgroundTasks):
    """Deploy a new WINEJS instance"""
    
    # Generate deployment ID and passwords
    deployment_id = generate_random_id()
    root_password = request.root_password or generate_password()
    fileserver_password = request.fileserver_password or generate_password(16)
    dumbdrop_pin = request.dumbdrop_pin or generate_pin()
    milkshape_vnc_pass = generate_password(8)
    
    # Prepare config for script rendering
    script_config = {
        "MAIN_DOMAIN": f"{request.subdomain}.{request.domain}",
        "SSL_EMAIL": request.email,
        "FILESERVER_PASS": fileserver_password,
        "DUMBDROP_PIN": dumbdrop_pin,
        "MILKSHAPE_VNC_PASS": milkshape_vnc_pass,
        "DROPLET_IP": "0.0.0.0",  # Will be replaced at runtime
        "ALLOWED_EXTENSIONS": ".ms3d,.obj,.3ds,.fbx,.png,.jpg,.mp3,.mp4"
    }
    
    # Render and upload script
    script_content = render_winejs_script(script_config)
    script_filename = f"winejs-{deployment_id}-{int(time.time())}.sh"
    installer_url = upload_to_spaces(script_content, script_filename)
    
    # Create cloud-init user-data
    user_data = create_cloudinit_userdata(installer_url, root_password)
    
    # Create droplet
    droplet = create_droplet_with_cloudinit({
        'deployment_id': deployment_id,
        'region': request.region,
        'droplet_size': request.droplet_size,
        'subdomain': request.subdomain
    }, user_data)
    
    # Wait for IP and setup DNS
    droplet_ip = wait_for_droplet_ip(droplet['id'])
    setup_dns(request.subdomain, request.domain, droplet_ip)
    
    # Build response
    response = DeploymentResponse(
        deployment_id=deployment_id,
        droplet_id=droplet['id'],
        droplet_ip=droplet_ip,
        subdomain=request.subdomain,
        domain=request.domain,
        url=f"https://{request.subdomain}.{request.domain}",
        upload_url=f"https://{request.subdomain}.{request.domain}/upload",
        download_url=f"https://{request.subdomain}.{request.domain}/download",
        installer_url=installer_url,
        root_password=root_password,
        fileserver_password=fileserver_password,
        dumbdrop_pin=dumbdrop_pin,
        milkshape_vnc_pass=milkshape_vnc_pass,
        status="provisioning"
    )
    
    # Optional webhook notification
    if request.webhook_url:
        background_tasks.add_task(notify_webhook, request.webhook_url, response.dict())
    
    return response

@app.get("/status/{deployment_id}")
async def get_status(deployment_id: str):
    """Check deployment status"""
    # You'd need to track this in a database
    return {"deployment_id": deployment_id, "status": "provisioning"}

@app.delete("/destroy/{droplet_id}")
async def destroy_droplet(droplet_id: int, subdomain: str, domain: str = DOMAIN):
    """Destroy droplet and clean up DNS"""
    try:
        # Delete DNS record
        records = do_client.domains.list_records(domain_name=domain)
        if records and 'domain_records' in records:
            for record in records['domain_records']:
                if record['type'] == 'A' and record['name'] == subdomain:
                    do_client.domains.delete_record(
                        domain_name=domain, 
                        record_id=record['id']
                    )
        
        # Delete droplet
        do_client.droplets.destroy(droplet_id=droplet_id)
        
        return {"status": "destroyed", "droplet_id": droplet_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def notify_webhook(url: str, data: dict):
    """Notify webhook when ready"""
    import httpx
    async with httpx.AsyncClient() as client:
        await client.post(url, json=data)

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "WINEJS Deployment API"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000) 

# 2. Jinja2 Template (templates/setup.sh.j2):

# This is your existing WINEJS script, but with Jinja2 variables:
# #!/bin/bash
# # Auto-generated WINEJS installer
# # DO NOT EDIT - Generated on {{ now() }}

# # ============= CONFIGURATION =============
# MAIN_DOMAIN="{{ MAIN_DOMAIN }}"
# SSL_EMAIL="{{ SSL_EMAIL }}"
# FILESERVER_PASS="{{ FILESERVER_PASS }}"
# DUMBDROP_PIN="{{ DUMBDROP_PIN }}"
# MILKSHAPE_VNC_PASS="{{ MILKSHAPE_VNC_PASS }}"
# ALLOWED_EXTENSIONS="{{ ALLOWED_EXTENSIONS }}"

# # ... REST OF YOUR EXISTING WINEJS SCRIPT HERE ...
# # (Copy your entire script here)

# 3. Requirements (requirements.txt):
# fastapi==0.104.1
# uvicorn[standard]==0.24.0
# pydo==0.28.0
# python-dotenv==1.0.0
# boto3==1.34.0
# jinja2==3.1.2
# httpx==0.25.1
# pydantic==2.5.0

# 4. Environment (.env):
# DIGITALOCEAN_TOKEN=your_do_token_here
# SPACES_KEY=your_spaces_key
# SPACES_SECRET=your_spaces_secret
# SPACES_REGION=lon1
# SPACES_BUCKET=winejs-installers
# DOMAIN=sdappnet.cloud
# VPC_UUID=d7ad8c4c-6258-4656-82a5-51af9523f641

# 🚀 How It Works:
#     API Call: POST /deploy with your config
#     Generate Script: Renders your WINEJS script with custom values
#     Upload to Spaces: Stores script privately, gets secure URL
#     Cloud-Init: Creates droplet with user-data that:
#         Downloads the script from private Spaces URL
#         Runs it automatically on first boot
#         Reports completion

#     DNS Setup: Creates wine.sdappnet.cloud A record
#     Response: Returns all credentials and URLs

# 🔥 Example API Usage:
# # Deploy a new WINEJS instance
# curl -X POST https://api.your-server.com/deploy \
#   -H "Content-Type: application/json" \
#   -d '{
#     "subdomain": "games",
#     "droplet_size": "s-2vcpu-4gb-amd",
#     "region": "nyc1",
#     "email": "admin@example.com"
#   }'

# # Response:
# {
#   "deployment_id": "a1b2c3d4",
#   "droplet_id": 12345678,
#   "droplet_ip": "142.93.1.1",
#   "url": "https://games.sdappnet.cloud",
#   "installer_url": "https://lon1.digitaloceanspaces.com/winejs-installers/winejs-a1b2c3d4.sh?X-Amz...",
#   "root_password": "FuckYou11!!a",
#   "fileserver_password": "k#J2$mP9@xL5",
#   "dumbdrop_pin": "847362",
#   "milkshape_vnc_pass": "xK9#mP2$",
#   "status": "provisioning"
# }

# # Check status
# curl https://api.your-server.com/status/a1b2c3d4

# # Destroy when done
# curl -X DELETE "https://api.your-server.com/destroy/12345678?subdomain=games"

# 🎯 The Complete Flow:

# User → API → Generate Script → Upload to Spaces → Create Droplet with Cloud-Init
#       ↓
#     DNS Record Created
#       ↓
#     Droplet Boots → Downloads Script → Runs WINEJS Install
#       ↓
#     MilkShape, Upload, Download ready at https://games.sdappnet.cloud