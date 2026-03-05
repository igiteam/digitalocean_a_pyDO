#!/usr/bin/env python3
"""
DigitalOcean Droplet Terminal Launcher
Lists all droplets and opens the browser terminal for your selection
"""

import os
import sys
import webbrowser
from pydo import Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
TOKEN = os.getenv('DIGITALOCEAN_TOKEN', "your_digitalocean_api_token_here")

# Color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    CYAN = '\033[96m'
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
            print("-" * 90)
            
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
                
                # Check if it has the wine-subdomain tag
                tags = droplet.get('tags', [])
                wine_tag = " 🍷" if 'wine-subdomain' in tags else ""
                
                print(f"{i}. {Colors.BOLD}{droplet['name']}{wine_tag}{Colors.END}")
                print(f"   🆔 ID: {droplet['id']}")
                print(f"   🌐 IP: {ip_address}")
                print(f"   📍 Region: {droplet['region']['slug']}")
                print(f"   💾 Size: {droplet['size']['slug']}")
                print(f"   {status_color}📊 Status: {status}{Colors.END}")
                print(f"   🔖 Tags: {', '.join(tags) if tags else 'None'}")
                print("-" * 90)
            
            return droplets
        else:
            print_color("Failed to fetch droplets.", Colors.RED)
            return []
            
    except Exception as e:
        print_color(f"❌ Error fetching droplets: {e}", Colors.RED)
        return []

def open_droplet_terminal(droplet_id, droplet_name):
    """Open the droplet's web terminal in browser"""
    terminal_url = f"https://cloud.digitalocean.com/droplets/{droplet_id}/terminal/ui/"
    print_color(f"\n🔗 Opening terminal for {droplet_name}...", Colors.CYAN)
    print(f"   URL: {terminal_url}")
    webbrowser.open(terminal_url)
    return True

def open_by_id(client, droplet_id):
    """Open terminal for a specific droplet ID"""
    try:
        # Get droplet details first
        response = client.droplets.get(droplet_id=droplet_id)
        if response and 'droplet' in response:
            droplet = response['droplet']
            droplet_name = droplet['name']
            
            print_color(f"\n📋 Found droplet: {droplet_name} ({droplet_id})", Colors.BOLD)
            open_droplet_terminal(droplet_id, droplet_name)
            return True
        else:
            print_color(f"❌ No droplet found with ID: {droplet_id}", Colors.RED)
            return False
            
    except Exception as e:
        print_color(f"❌ Error: {e}", Colors.RED)
        return False

def main():
    """Main terminal launcher function"""
    print_color("🚀 DigitalOcean Droplet Terminal Launcher", Colors.HEADER + Colors.BOLD)
    print("=" * 60)
    print_color("🌐 Select a droplet to open its web terminal", Colors.CYAN)
    print("=" * 60)
    
    # Initialize client
    client = init_client()
    if not client:
        return
    
    # Check if ID was provided as command line argument
    if len(sys.argv) > 1:
        try:
            droplet_id = int(sys.argv[1])
            open_by_id(client, droplet_id)
            return
        except ValueError:
            print_color("❌ Invalid droplet ID. Running in interactive mode...", Colors.YELLOW)
    
    # List all droplets
    droplets = list_all_droplets(client)
    
    if not droplets:
        return
    
    # Get user selection
    while True:
        try:
            choice = input(f"\n{Colors.BOLD}Enter droplet number to open terminal (or 'q' to quit): {Colors.END}")
            
            if choice.lower() == 'q':
                print_color("👋 Exiting...", Colors.BLUE)
                return
            
            idx = int(choice) - 1
            if 0 <= idx < len(droplets):
                selected = droplets[idx]
                droplet_id = selected['id']
                droplet_name = selected['name']
                
                # Open the terminal
                open_droplet_terminal(droplet_id, droplet_name)
                return
                # Ask if they want to open another
                # again = input(f"\n{Colors.BOLD}Open another terminal? (y/n): {Colors.END}").lower()
                # if again != 'y':
                #     print_color("👋 Exiting...", Colors.BLUE)
                #     return
                
                # Refresh list
                droplets = list_all_droplets(client)
                if not droplets:
                    return
            else:
                print_color(f"❌ Please enter a number between 1 and {len(droplets)}", Colors.RED)
                
        except ValueError:
            print_color("❌ Please enter a valid number", Colors.RED)
        except KeyboardInterrupt:
            print_color("\n👋 Exiting...", Colors.BLUE)
            return

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_color("\n\n👋 Operation cancelled by user.", Colors.BLUE)
    except Exception as e:
        print_color(f"\n❌ Unexpected error: {e}", Colors.RED)