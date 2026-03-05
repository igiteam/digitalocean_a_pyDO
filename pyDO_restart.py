#!/usr/bin/env python3
"""
Droplet Restart Tool for DigitalOcean
Lists droplets and restarts the one you select
"""

import os
import sys
import time
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
                
                print(f"{i}. {Colors.BOLD}{droplet['name']}{Colors.END}")
                print(f"   🆔 ID: {droplet['id']}")
                print(f"   🌐 IP: {ip_address}")
                print(f"   📍 Region: {droplet['region']['slug']}")
                print(f"   💾 Size: {droplet['size']['slug']}")
                print(f"   {status_color}📊 Status: {status}{Colors.END}")
                print(f"   🔖 Tags: {', '.join(droplet.get('tags', ['None']))}")
                print("-" * 90)
            
            return droplets
        else:
            print_color("Failed to fetch droplets.", Colors.RED)
            return []
            
    except Exception as e:
        print_color(f"❌ Error fetching droplets: {e}", Colors.RED)
        return []

def restart_droplet(client, droplet_id, droplet_name):
    """Restart a droplet"""
    try:
        print_color(f"   🔄 Restarting {droplet_name}...", Colors.YELLOW)
        
        # Send the restart action
        response = client.droplet_actions.post(
            droplet_id=droplet_id,
            body={"type": "reboot"}
        )
        
        if response and 'action' in response:
            action = response['action']
            print_color(f"   ✅ Restart initiated! Action ID: {action['id']}", Colors.GREEN)
            return True
        else:
            print_color(f"   ❌ Failed to initiate restart", Colors.RED)
            return False
            
    except Exception as e:
        print_color(f"   ❌ Failed to restart droplet: {e}", Colors.RED)
        return False

def main():
    """Main restart function"""
    print_color("🚀 DigitalOcean Droplet Restart Tool", Colors.HEADER + Colors.BOLD)
    print("=" * 60)
    print_color("🔄 Select a droplet to restart", Colors.CYAN)
    print("=" * 60)
    
    # Initialize client
    client = init_client()
    if not client:
        return
    
    # Check if ID was provided as command line argument
    if len(sys.argv) > 1:
        try:
            droplet_id = int(sys.argv[1])
            # Get droplet details
            response = client.droplets.get(droplet_id=droplet_id)
            if response and 'droplet' in response:
                droplet = response['droplet']
                droplet_name = droplet['name']
                print_color(f"\n📋 Restarting droplet: {droplet_name} ({droplet_id})", Colors.BOLD)
                restart_droplet(client, droplet_id, droplet_name)
            else:
                print_color(f"❌ No droplet found with ID: {droplet_id}", Colors.RED)
            return
        except ValueError:
            print_color("❌ Invalid droplet ID", Colors.RED)
            return
    
    # List all droplets
    droplets = list_all_droplets(client)
    
    if not droplets:
        return
    
    # Get user selection
    while True:
        try:
            choice = input(f"\n{Colors.BOLD}Enter droplet number to restart (or 'q' to quit): {Colors.END}")
            
            if choice.lower() == 'q':
                print_color("👋 Exiting...", Colors.BLUE)
                return
            
            idx = int(choice) - 1
            if 0 <= idx < len(droplets):
                selected = droplets[idx]
                
                # Confirm restart
                droplet_id = selected['id']
                droplet_name = selected['name']
                
                print_color(f"\n📋 Selected: {droplet_name}", Colors.BOLD)
                confirm = input(f"Restart this droplet? (y/n): ").lower()
                
                if confirm == 'y':
                    restart_droplet(client, droplet_id, droplet_name)
                else:
                    print_color("👋 Restart cancelled.", Colors.BLUE)
                
                # Ask if they want to restart another
                again = input(f"\n{Colors.BOLD}Restart another droplet? (y/n): {Colors.END}").lower()
                if again != 'y':
                    print_color("👋 Exiting...", Colors.BLUE)
                    return
                
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