#!/usr/bin/env python3
"""
Example usage of the agent update client.
Demonstrates how to check for updates, download, and install them.
"""

import asyncio
import logging
from agent.updater import UpdateClient, UpdateStatus, VersionManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def progress_callback(status: str, progress: float, message: str):
    """Progress callback for update operations."""
    print(f"[{status.upper()}] {progress:5.1f}% - {message}")


async def check_and_perform_update():
    """Example of checking for and performing an update."""
    
    # Initialize update client
    client = UpdateClient(
        update_server_url="https://update.example.com",
        agent_id="agent-001",
        api_key="your-api-key-here",
        install_dir="/opt/network-probe-agent",
        backup_dir="/opt/network-probe-agent/backup"
    )
    
    # Set progress callback
    client.set_progress_callback(progress_callback)
    
    try:
        async with client:
            print("🔍 Checking for updates...")
            
            # Check for available updates
            update_info = await client.check_for_updates()
            
            if not update_info:
                print("✅ No updates available")
                return
            
            print(f"📦 Update available: {update_info['version']}")
            print(f"📝 Description: {update_info.get('description', 'No description')}")
            
            if update_info.get('changelog'):
                print("📋 Changelog:")
                for change in update_info['changelog']:
                    print(f"  - {change}")
            
            # Ask user for confirmation (in real usage)
            print("\n🤔 Do you want to proceed with the update? (y/n)")
            # For this example, we'll assume yes
            proceed = True  # input().lower().startswith('y')
            
            if not proceed:
                print("❌ Update cancelled by user")
                return
            
            print("\n🚀 Starting update process...")
            
            # Perform the complete update
            success = await client.perform_update(auto_restart=False)
            
            if success:
                print("✅ Update completed successfully!")
                print("🔄 Please restart the agent to use the new version")
            else:
                print("❌ Update failed!")
                
                # Check if we can rollback
                print("🔄 Attempting rollback...")
                if client.rollback_update():
                    print("✅ Rollback successful")
                else:
                    print("❌ Rollback failed - manual intervention required")
    
    except Exception as e:
        logger.error(f"Update process failed: {e}")
        print(f"❌ Update process failed: {e}")


async def manual_update_steps():
    """Example of performing update steps manually."""
    
    client = UpdateClient(
        update_server_url="https://update.example.com",
        agent_id="agent-001",
        api_key="your-api-key-here"
    )
    
    client.set_progress_callback(progress_callback)
    
    try:
        async with client:
            # Step 1: Check for updates
            print("Step 1: Checking for updates...")
            update_info = await client.check_for_updates()
            
            if not update_info:
                print("No updates available")
                return
            
            # Step 2: Download update
            print("Step 2: Downloading update...")
            package_path = await client.download_update(update_info)
            
            if not package_path:
                print("Download failed")
                return
            
            # Step 3: Verify package
            print("Step 3: Verifying package...")
            if not client.verify_update_package(package_path):
                print("Package verification failed")
                return
            
            # Step 4: Install update
            print("Step 4: Installing update...")
            if not client.install_update(package_path):
                print("Installation failed")
                return
            
            # Step 5: Schedule restart (optional)
            print("Step 5: Scheduling restart...")
            client.schedule_restart(delay_seconds=10)
            
            print("✅ Update process completed!")
    
    except Exception as e:
        logger.error(f"Manual update failed: {e}")


def check_current_version():
    """Example of checking current version."""
    
    version_manager = VersionManager()
    current_version = version_manager.get_current_version()
    
    if current_version:
        print(f"Current version: {current_version}")
        
        version_info = version_manager.get_version_info()
        print("Version details:")
        for key, value in version_info.items():
            print(f"  {key}: {value}")
    else:
        print("Could not determine current version")


def cleanup_old_backups():
    """Example of cleaning up old backups."""
    
    client = UpdateClient(
        update_server_url="https://update.example.com",
        agent_id="agent-001",
        api_key="your-api-key-here"
    )
    
    print("Cleaning up old backups...")
    deleted_count = client.cleanup_old_backups(keep_count=3)
    print(f"Deleted {deleted_count} old backup files")


async def main():
    """Main example function."""
    
    print("🔧 Agent Update Client Examples\n")
    
    # Example 1: Check current version
    print("=" * 50)
    print("Example 1: Check Current Version")
    print("=" * 50)
    check_current_version()
    
    # Example 2: Check and perform update (automated)
    print("\n" + "=" * 50)
    print("Example 2: Automated Update Process")
    print("=" * 50)
    await check_and_perform_update()
    
    # Example 3: Manual update steps
    print("\n" + "=" * 50)
    print("Example 3: Manual Update Steps")
    print("=" * 50)
    await manual_update_steps()
    
    # Example 4: Cleanup old backups
    print("\n" + "=" * 50)
    print("Example 4: Cleanup Old Backups")
    print("=" * 50)
    cleanup_old_backups()
    
    print("\n✨ Examples completed!")


if __name__ == '__main__':
    asyncio.run(main())