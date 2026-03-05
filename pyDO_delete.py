import os
import sys
import time
from pydo import Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
TOKEN = os.getenv('DIGITALOCEAN_TOKEN_DELETE', "your_digitalocean_api_token_here")
DOMAIN = os.getenv('DOMAIN', "sdappnet.cloud")

# Color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'

def print_color(text, color):
    """Print colored text"""
    print(f"{color}{text}{Colors.END}")

def init_client():
    """Initialize the PyDo client"""
    if TOKEN == "your_digitalocean_api_token_here":
        print_color("❌ Please set your DigitalOcean API token!", Colors.RED)
        print("📝 You can generate one at: https://cloud.digitalocean.com/account/api/tokens")
        print("📝 Or create a .env file with DIGITALOCEAN_TOKEN=your_token")
        return None
    
    return Client(token=TOKEN)

def list_all_droplets(client):
    """List all droplets in the account"""
    print_color("\n📋 Fetching your droplets...", Colors.BLUE)
    
    try:
        response = client.droplets.list()
        
        if response and 'droplets' in response:
            droplets = response['droplets']
            
            if not droplets:
                print_color("No droplets found in your account.", Colors.YELLOW)
                return []
            
            print_color(f"\nFound {len(droplets)} droplet(s):", Colors.BOLD)
            print("-" * 80)
            
            for i, droplet in enumerate(droplets, 1):
                # Get droplet IP
                ip_address = "No IP"
                if 'networks' in droplet and 'v4' in droplet['networks']:
                    for network in droplet['networks']['v4']:
                        if network['type'] == 'public':
                            ip_address = network['ip_address']
                            break
                
                # Status with color
                status = droplet['status']
                status_color = Colors.GREEN if status == 'active' else Colors.YELLOW
                
                print(f"{i}. {Colors.BOLD}{droplet['name']}{Colors.END}")
                print(f"   🆔 ID: {droplet['id']}")
                print(f"   🌐 IP: {ip_address}")
                print(f"   📍 Region: {droplet['region']['slug']}")
                print(f"   💾 Size: {droplet['size']['slug']}")
                print(f"   {status_color}📊 Status: {status}{Colors.END}")
                print(f"   🔖 Tags: {', '.join(droplet.get('tags', ['None']))}")
                print("-" * 80)
            
            return droplets
        else:
            print_color("Failed to fetch droplets.", Colors.RED)
            return []
            
    except Exception as e:
        print_color(f"❌ Error fetching droplets: {e}", Colors.RED)
        return []

def find_dns_records_for_ip(client, ip_address):
    """Find all DNS records pointing to a specific IP"""
    records_found = []
    
    try:
        # Get all domain records for your domain
        response = client.domains.list_records(domain_name=DOMAIN)
        
        if response and 'domain_records' in response:
            for record in response['domain_records']:
                if record['type'] == 'A' and record.get('data') == ip_address:
                    records_found.append({
                        'id': record['id'],
                        'name': record['name'],
                        'type': record['type'],
                        'data': record['data']
                    })
    except Exception as e:
        print_color(f"⚠️ Error fetching DNS records: {e}", Colors.YELLOW)
    
    return records_found

def delete_dns_record(client, record_id, record_name):
    """Delete a specific DNS record - FIXED using docs"""
    try:
        print_color(f"   🗑️  Deleting DNS record: {record_name}.{DOMAIN}...", Colors.YELLOW)
        # CORRECT METHOD from docs: client.domains.delete_record(domain_name="example.com", domain_record_id=3352896)
        client.domains.delete_record(domain_name=DOMAIN, domain_record_id=record_id)
        print_color(f"   ✅ DNS record deleted!", Colors.GREEN)
        return True
    except Exception as e:
        print_color(f"   ❌ Failed to delete DNS record: {e}", Colors.RED)
        return False

def delete_droplet(client, droplet_id, droplet_name):
    """Delete a specific droplet - FIXED using docs"""
    try:
        print_color(f"   🖥️  Deleting droplet: {droplet_name}...", Colors.YELLOW)
        # CORRECT METHOD from docs: client.droplets.destroy(droplet_id=553456)
        client.droplets.destroy(droplet_id=droplet_id)
        print_color(f"   ✅ Droplet deleted!", Colors.GREEN)
        return True
    except Exception as e:
        print_color(f"   ❌ Failed to delete droplet: {e}", Colors.RED)
        return False

def show_progress(message, duration=2):
    """Show a simple progress animation"""
    print(f"{message}", end="", flush=True)
    for i in range(duration):
        time.sleep(0.5)
        print(".", end="", flush=True)
    print(" Done!")

def main():
    """Main deletion function"""
    print_color("🚀 DigitalOcean Droplet Deletion Tool", Colors.HEADER + Colors.BOLD)
    print("=" * 60)
    print_color("⚠️  WARNING: This tool will delete droplets and DNS records!", Colors.RED + Colors.BOLD)
    print("=" * 60)
    
    # Initialize client
    client = init_client()
    if not client:
        return
    
    # List all droplets
    droplets = list_all_droplets(client)
    
    if not droplets:
        return
    
    # Get user selection
    while True:
        try:
            choice = input(f"\n{Colors.BOLD}Enter droplet number to delete (or 'q' to quit): {Colors.END}")
            
            if choice.lower() == 'q':
                print_color("👋 Exiting...", Colors.BLUE)
                return
            
            idx = int(choice) - 1
            if 0 <= idx < len(droplets):
                selected = droplets[idx]
                break
            else:
                print_color(f"❌ Please enter a number between 1 and {len(droplets)}", Colors.RED)
        except ValueError:
            print_color("❌ Please enter a valid number", Colors.RED)
        except KeyboardInterrupt:
            print_color("\n👋 Exiting...", Colors.BLUE)
            return
    
    # Get droplet details
    droplet_id = selected['id']
    droplet_name = selected['name']
    
    # Get droplet IP
    droplet_ip = None
    if 'networks' in selected and 'v4' in selected['networks']:
        for network in selected['networks']['v4']:
            if network['type'] == 'public':
                droplet_ip = network['ip_address']
                break
    
    print_color(f"\n📋 Selected droplet:", Colors.BOLD)
    print(f"   🖥️  Name: {droplet_name}")
    print(f"   🆔 ID: {droplet_id}")
    print(f"   🌐 IP: {droplet_ip or 'Unknown'}")
    
    # Check for DNS records pointing to this droplet
    dns_records = []
    if droplet_ip:
        dns_records = find_dns_records_for_ip(client, droplet_ip)
    
    if dns_records:
        print_color(f"\n🔗 Found DNS record(s) pointing to this droplet:", Colors.YELLOW)
        for record in dns_records:
            record_name = f"{record['name']}.{DOMAIN}" if record['name'] != '@' else DOMAIN
            print(f"   • {record['type']} {record_name} -> {record['data']}")
        
        # Confirm DNS deletion
        print_color(f"\n⚠️  Deleting this droplet will break these DNS records!", Colors.RED + Colors.BOLD)
        confirm_dns = input(f"Delete DNS records along with droplet? (y/n): ").lower()
        
        if confirm_dns == '' or confirm_dns == 'y':
            print_color(f"\n🔄 Starting cleanup process...", Colors.BLUE)
            
            # Delete DNS records first
            print_color(f"\n📝 Step 1/2: Cleaning up DNS records...", Colors.BOLD)
            for record in dns_records:
                record_name = record['name']
                delete_dns_record(client, record['id'], record_name)
                show_progress("   Progress")
            
            # Delete droplet
            print_color(f"\n📝 Step 2/2: Deleting droplet...", Colors.BOLD)
            if delete_droplet(client, droplet_id, droplet_name):
                show_progress("   Progress")
                print_color(f"\n✅ Cleanup complete! DNS records and droplet have been deleted.", Colors.GREEN)
            else:
                print_color(f"\n❌ Droplet deletion failed. DNS records were deleted but droplet remains.", Colors.RED)
        else:
            print_color(f"\n⏸️  Keeping DNS records. Proceed with droplet deletion only?", Colors.YELLOW)
            confirm_droplet_only = input(f"Delete droplet ONLY? (y/n): ").lower()
            
            if confirm_droplet_only == 'y':
                print_color(f"\n📝 Deleting droplet only...", Colors.BOLD)
                if delete_droplet(client, droplet_id, droplet_name):
                    show_progress("   Progress")
                    print_color(f"\n✅ Droplet deleted. DNS records remain intact.", Colors.GREEN)
                    print_color(f"⚠️  Note: DNS records still point to {droplet_ip} which no longer exists!", Colors.YELLOW)
                else:
                    print_color(f"\n❌ Droplet deletion failed.", Colors.RED)
            else:
                print_color(f"\n👋 Operation cancelled. No changes made.", Colors.BLUE)
    else:
        # No DNS records found
        print_color(f"\n🔗 No DNS records found pointing to this droplet.", Colors.GREEN)
        
        # Confirm droplet deletion
        print_color(f"\n⚠️  Are you sure you want to delete this droplet?", Colors.RED + Colors.BOLD)
        confirm = input(f"Delete droplet '{droplet_name}'? (y/n): ").lower()
        
        if confirm_dns == '' or confirm == 'y':
            print_color(f"\n📝 Deleting droplet...", Colors.BOLD)
            if delete_droplet(client, droplet_id, droplet_name):
                show_progress("   Progress")
                print_color(f"\n✅ Droplet deleted successfully!", Colors.GREEN)
            else:
                print_color(f"\n❌ Droplet deletion failed.", Colors.RED)
        else:
            print_color(f"\n👋 Operation cancelled. No changes made.", Colors.BLUE)

def quick_delete_by_id(client, droplet_id):
    """Quick delete a droplet by ID (for automation)"""
    try:
        # Get droplet details first
        response = client.droplets.get(droplet_id=droplet_id)
        if response and 'droplet' in response:
            droplet = response['droplet']
            droplet_name = droplet['name']
            
            print_color(f"🗑️  Quickly deleting droplet: {droplet_name} ({droplet_id})", Colors.YELLOW)
            client.droplets.destroy(droplet_id=droplet_id)
            print_color(f"✅ Droplet deleted!", Colors.GREEN)
            return True
    except Exception as e:
        print_color(f"❌ Failed to delete droplet: {e}", Colors.RED)
        return False

if __name__ == "__main__":
    try:
        # Check for command line argument (quick delete by ID)
        if len(sys.argv) > 1 and sys.argv[1] == "--quick" and len(sys.argv) > 2:
            client = init_client()
            if client:
                quick_delete_by_id(client, sys.argv[2])
        else:
            # Interactive mode
            main()
    except KeyboardInterrupt:
        print_color("\n\n👋 Operation cancelled by user.", Colors.BLUE)
    except Exception as e:
        print_color(f"\n❌ Unexpected error: {e}", Colors.RED)