#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple DNS Tester for WINEJS - UNIVERSAL VERSION
Works with ALL versions of dnspython
"""

import socket
import sys
import time
from datetime import datetime

# Try to import dnspython, install if missing
try:
    import dns.resolver
    import dns.exception
except ImportError:
    print("Installing dnspython...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "dnspython"])
    import dns.resolver
    import dns.exception

class DNSTester:
    def __init__(self, domain, subdomain=None, expected_ip=None):
        self.domain = domain
        self.subdomain = subdomain
        if subdomain:
            self.full_domain = subdomain + "." + domain
        else:
            self.full_domain = domain
        self.expected_ip = expected_ip

    def print_result(self, status, text):
        if status == "ok":
            print("[OK] " + text)
        elif status == "wait":
            print("[..] " + text)
        elif status == "error":
            print("[ERROR] " + text)
        elif status == "info":
            print("[INFO] " + text)
        elif status == "header":
            print("\n" + "="*60)
            print(text)
            print("="*60)

    def get_dns_answer(self, domain):
        """Universal DNS lookup that works with any dnspython version"""
        resolver = dns.resolver.Resolver()
        
        # Try different methods (query, resolve) for compatibility
        try:
            # Method 1: resolve (newer versions)
            answers = resolver.resolve(domain, 'A')
            return answers
        except AttributeError:
            try:
                # Method 2: query (older versions)
                answers = resolver.query(domain, 'A')
                return answers
            except AttributeError:
                # Method 3: direct lookup
                import subprocess
                import re
                try:
                    result = subprocess.check_output(["dig", "+short", domain]).decode().strip()
                    if result:
                        class FakeAnswer:
                            def __init__(self, ip):
                                self.ip = ip
                            def __str__(self):
                                return self.ip
                        return [FakeAnswer(result)]
                except:
                    pass
        return None

    def test_a_record(self):
        """Test A record resolution"""
        self.print_result("header", "Testing A Record: " + self.full_domain)

        try:
            # System resolver check
            system_ip = socket.gethostbyname(self.full_domain)
            self.print_result("ok", "System resolver: " + self.full_domain + " -> " + system_ip)

            # Try DNS lookup with universal method
            answers = self.get_dns_answer(self.full_domain)
            
            if answers:
                print("\nDetailed DNS Results:")
                for i, answer in enumerate(answers, 1):
                    ip = str(answer)
                    print("  Record " + str(i) + ": " + ip)
                    
                    # Try to get TTL if available
                    try:
                        if hasattr(answer, 'ttl'):
                            ttl = answer.ttl
                            print("    TTL: " + str(ttl) + " seconds (" + str(ttl//60) + " minutes)")
                    except:
                        pass
            else:
                print("\n[INFO] Using system resolver only")

            # Compare with expected IP
            if self.expected_ip:
                print("")
                if system_ip == self.expected_ip:
                    self.print_result("ok", "IP matches expected: " + system_ip)
                else:
                    self.print_result("wait", "Current IP (" + system_ip + ") differs from expected (" + self.expected_ip + ")")
                    self.print_result("info", "DNS propagation can take 5-30 minutes")

            return system_ip

        except socket.gaierror:
            self.print_result("error", "Could not resolve " + self.full_domain)
            return None
        except Exception as e:
            self.print_result("error", "Error: " + str(e))
            return None

    def test_multiple_resolvers(self):
        """Test DNS from multiple servers"""
        self.print_result("header", "Testing Multiple DNS Servers")

        resolvers = [
            ('8.8.8.8', 'Google DNS'),
            ('1.1.1.1', 'Cloudflare DNS'),
            ('208.67.222.222', 'OpenDNS'),
        ]

        for resolver_ip, resolver_name in resolvers:
            try:
                # Try using dig command (most reliable)
                import subprocess
                try:
                    result = subprocess.check_output(
                        ["dig", "@" + resolver_ip, "+short", self.full_domain], 
                        timeout=3,
                        stderr=subprocess.DEVNULL
                    ).decode().strip()
                    
                    if result:
                        ip = result.split('\n')[0]  # Take first IP
                        if self.expected_ip and ip == self.expected_ip:
                            print("  ✓ " + resolver_name.ljust(15) + ": " + ip + " (matches)")
                        elif self.expected_ip:
                            print("  ? " + resolver_name.ljust(15) + ": " + ip + " (different)")
                        else:
                            print("  • " + resolver_name.ljust(15) + ": " + ip)
                    else:
                        print("  ✗ " + resolver_name.ljust(15) + ": No answer")
                except:
                    print("  ✗ " + resolver_name.ljust(15) + ": Failed")
            except:
                print("  ✗ " + resolver_name.ljust(15) + ": Failed")

    def run(self):
        """Run all tests"""
        print("\n" + "="*60)
        print("DNS TESTER FOR WINEJS")
        print("Domain: " + self.full_domain)
        if self.expected_ip:
            print("Expected IP: " + self.expected_ip)
        print("Time: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        print("="*60)

        ip = self.test_a_record()

        if ip:
            self.test_multiple_resolvers()

            print("\n" + "="*60)
            print("SUMMARY")
            print("="*60)

            if self.expected_ip:
                if ip == self.expected_ip:
                    print("[OK] DNS is correctly set to " + ip)
                    print("Site should be accessible at: http://" + self.full_domain)
                else:
                    print("[..] DNS propagation in progress")
                    print("      Current: " + ip)
                    print("      Expected: " + self.expected_ip)
                    print("      Wait 5-30 minutes")
            else:
                print("[OK] DNS resolves to " + ip)

def show_help():
    """Show help information"""
    print("\n" + "="*60)
    print("DNS TESTER FOR WINEJS - HELP")
    print("="*60)
    print("\nUsage: python pyDO_dns.py DOMAIN [options]")
    print("\nArguments:")
    print("  DOMAIN               Main domain (e.g., sdappnet.cloud)")
    print("\nOptions:")
    print("  -s, --subdomain      Subdomain (default: wine)")
    print("  -i, --ip             Expected IP address for propagation check")
    print("  -w, --watch SECONDS  Watch mode - check every N seconds")
    print("\nExamples:")
    print("  python pyDO_dns.py sdappnet.cloud")
    print("  python pyDO_dns.py sdappnet.cloud -s www")
    print("  python pyDO_dns.py sdappnet.cloud -s wine -i 192.168.1.100")
    print("  python pyDO_dns.py sdappnet.cloud -s wine -i 192.168.1.100 -w 10")
    print("="*60)

def interactive_mode():
    """Interactive mode - prompt user for input"""
    print("\n" + "="*60)
    print("DNS TESTER FOR WINEJS - INTERACTIVE MODE")
    print("="*60)
    
    # Get domain
    while True:
        domain = input("\nEnter domain (e.g., sdappnet.cloud): ").strip()
        if domain:
            break
        print("Domain cannot be empty!")
    
    # Get subdomain (optional)
    subdomain = input("Enter subdomain (press Enter for 'wine'): ").strip()
    if not subdomain:
        subdomain = "wine"
        print("Using default subdomain: wine")
    
    # Get expected IP (optional)
    expected_ip = input("Enter expected IP (press Enter to skip): ").strip()
    if not expected_ip:
        expected_ip = None
    
    # Get watch mode (optional)
    watch = input("Watch mode in seconds? (press Enter to skip): ").strip()
    
    return domain, subdomain, expected_ip, watch

def main():
    import argparse
    
    # If no arguments provided, show help and offer interactive mode
    if len(sys.argv) == 1:
        show_help()
        response = input("\nRun in interactive mode? (y/n): ").strip().lower()
        if response in ['y', 'yes']:
            domain, subdomain, expected_ip, watch = interactive_mode()
            
            # Create tester
            tester = DNSTester(domain, subdomain, expected_ip)
            
            # Run in watch mode if specified
            if watch and watch.isdigit():
                watch_seconds = int(watch)
                print("\nWatch mode - checking every " + str(watch_seconds) + " seconds")
                print("Press Ctrl+C to stop\n")
                try:
                    while True:
                        print("\n--- Check at " + datetime.now().strftime('%H:%M:%S') + " ---")
                        tester.test_a_record()
                        time.sleep(watch_seconds)
                except KeyboardInterrupt:
                    print("\nStopped")
            else:
                tester.run()
        else:
            print("\nUse: python pyDO_dns.py DOMAIN [-s SUBDOMAIN] [-i IP] [-w SECONDS]")
            print("Example: python pyDO_dns.py sdappnet.cloud -s wine")
        return
    
    # Parse arguments if provided
    parser = argparse.ArgumentParser(description='DNS Tester for WINEJS')
    parser.add_argument('domain', help='Domain (e.g., sdappnet.cloud)')
    parser.add_argument('-s', '--subdomain', help='Subdomain (default: wine)')
    parser.add_argument('-i', '--ip', help='Expected IP address')
    parser.add_argument('-w', '--watch', type=int, help='Watch mode (seconds)')

    args = parser.parse_args()

    subdomain = args.subdomain if args.subdomain else "wine"

    tester = DNSTester(args.domain, subdomain, args.ip)

    if args.watch:
        print("\nWatch mode - checking every " + str(args.watch) + " seconds")
        print("Press Ctrl+C to stop\n")
        try:
            while True:
                print("\n--- Check at " + datetime.now().strftime('%H:%M:%S') + " ---")
                tester.test_a_record()
                time.sleep(args.watch)
        except KeyboardInterrupt:
            print("\nStopped")
    else:
        tester.run()

if __name__ == "__main__":
    main()