"""
Example usage of Enhanced Gmail Prompts with Service Resources.

This script demonstrates how to use the new dynamic Gmail prompts that integrate
with the service list resources to create contextual, intelligent emails.

Run this script to see examples of:
1. Resource-aware email generation
2. Dynamic Gmail analytics
3. Context-driven optimization recommendations
4. Professional email templates with real Gmail data
"""

import asyncio
import logging
from fastmcp import FastMCP

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def demonstrate_dynamic_gmail_prompts():
    """
    Demonstrate the dynamic Gmail prompts with resource integration.
    """
    logger.info("🚀 Starting Enhanced Gmail Prompts Demo")
    
    # Initialize FastMCP (this would be done in your main server setup)
    mcp = FastMCP("enhanced-gmail-demo")
    
    print("=" * 80)
    print("🌟 ENHANCED GMAIL PROMPTS WITH SERVICE RESOURCES")
    print("=" * 80)
    print()
    
    # Example 1: Smart Email with Context
    print("📧 Example 1: Smart Email with Gmail Context")
    print("-" * 50)
    print("This prompt generates emails using real-time Gmail resource data:")
    print()
    print("Prompt: smart_email_with_context")
    print("Parameters:")
    print("  • email_subject: 'Intelligent Email with Gmail Data'")
    print("  • recipient_name: 'Tech Team'") 
    print("  • email_purpose: 'project collaboration'")
    print()
    print("🔗 Resource Integration:")
    print("  • service://gmail/lists - Discovers available Gmail resources")
    print("  • service://gmail/labels - Gets current Gmail labels")
    print("  • service://gmail/filters - Analyzes Gmail filter setup")
    print()
    print("📊 Generated Content:")
    print("  • Context-aware email body")
    print("  • Professional HTML design") 
    print("  • Dynamic resource information")
    print("  • Intelligent routing considerations")
    print()
    
    # Example 2: Gmail Analytics Report
    print("📊 Example 2: Gmail Analytics Report")
    print("-" * 50)
    print("This prompt creates comprehensive Gmail configuration analytics:")
    print()
    print("Prompt: gmail_analytics_report")
    print("Parameters:")
    print("  • report_title: 'Q4 Gmail Configuration Analysis'")
    print("  • analysis_focus: 'comprehensive'")
    print()
    print("🔍 Resource Analysis:")
    print("  • Real-time filter configuration analysis")
    print("  • Label organization assessment")
    print("  • Resource utilization metrics")
    print("  • Cross-resource correlation insights")
    print()
    print("📈 Report Features:")
    print("  • Executive summary with key metrics")
    print("  • Detailed resource breakdown")
    print("  • Health scoring and recommendations")
    print("  • Email-ready formatted output")
    print()
    
    # Example 3: Filter Optimization
    print("⚙️ Example 3: Gmail Filter Optimizer")
    print("-" * 50)
    print("This prompt provides data-driven filter optimization:")
    print()
    print("Prompt: gmail_filter_optimizer")
    print("Parameters:")
    print("  • optimization_goal: 'efficiency'")
    print("  • priority_level: 'high'")
    print()
    print("🎯 Optimization Analysis:")
    print("  • Duplicate filter detection")
    print("  • Complex filter simplification")
    print("  • Unused filter identification")
    print("  • Performance scoring")
    print()
    print("🚀 Implementation Guide:")
    print("  • Immediate action recommendations")
    print("  • Medium-term optimization goals")
    print("  • Long-term strategy planning")
    print("  • Progress monitoring setup")
    print()
    
    # Example 4: Enhanced Showcase
    print("🌟 Example 4: Enhanced Showcase Email")
    print("-" * 50)
    print("This prompt creates beautiful emails enhanced with Gmail intelligence:")
    print()
    print("Prompt: enhanced_html_email")
    print("Parameters:")
    print("  • email_subject: 'Welcome - Enhanced with Gmail Intelligence'")
    print("  • recipient_name: 'Valued Customer'")
    print()
    print("🧠 Intelligence Features:")
    print("  • Real-time Gmail resource discovery")
    print("  • Dynamic content adaptation")
    print("  • Context-aware styling")
    print("  • Professional responsive design")
    print()
    print("💼 Business Benefits:")
    print("  • Personalized communication")
    print("  • Intelligent email routing")
    print("  • Brand consistency")
    print("  • Automation compatibility")
    print()
    
    print("=" * 80)
    print("🎯 KEY ADVANTAGES OF RESOURCE-INTEGRATED PROMPTS")
    print("=" * 80)
    print()
    print("✨ Dynamic Content Generation:")
    print("   • Real-time data from Gmail configuration")
    print("   • Context-aware email templates")
    print("   • Intelligent content adaptation")
    print("   • Professional automated communications")
    print()
    print("📊 Advanced Analytics:")
    print("   • Live Gmail configuration analysis")
    print("   • Data-driven optimization recommendations") 
    print("   • Performance monitoring and tracking")
    print("   • Executive reporting capabilities")
    print()
    print("🚀 Automation Ready:")
    print("   • Integration with existing Gmail workflows")
    print("   • Scalable email generation system")
    print("   • Error handling and graceful fallbacks")
    print("   • Cross-platform compatibility")
    print()
    print("🔗 Resource Integration:")
    print("   • service:// URI pattern usage")
    print("   • Hierarchical resource access")
    print("   • Dynamic service discovery")
    print("   • Multi-resource correlation analysis")
    print()
    
    print("=" * 80)
    print("💡 HOW TO USE THESE PROMPTS")
    print("=" * 80)
    print()
    print("1. 📋 List Available Prompts:")
    print("   prompts = await client.list_prompts()")
    print("   gmail_prompts = [p for p in prompts if 'gmail' in p.tags]")
    print()
    print("2. 🧠 Use Smart Email Generation:")
    print("   result = await client.get_prompt('smart_email_with_context', {")
    print("       'email_subject': 'Your Subject',")
    print("       'recipient_name': 'Recipient Name',") 
    print("       'email_purpose': 'collaboration'")
    print("   })")
    print()
    print("3. 📊 Generate Analytics Report:")
    print("   analytics = await client.get_prompt('gmail_analytics_report', {")
    print("       'report_title': 'Gmail Config Analysis',")
    print("       'analysis_focus': 'comprehensive'")
    print("   })")
    print()
    print("4. ⚙️ Optimize Gmail Filters:")
    print("   optimization = await client.get_prompt('gmail_filter_optimizer', {")
    print("       'optimization_goal': 'efficiency',")
    print("       'priority_level': 'high'")
    print("   })")
    print()
    
    print("=" * 80)
    print("🌟 RESOURCE INTEGRATION SHOWCASE")
    print("=" * 80)
    print()
    print("These prompts demonstrate FastMCP2's advanced capabilities:")
    print()
    print("🔗 Service Resource Integration:")
    print("   • Dynamic discovery of Gmail resources")
    print("   • Real-time data integration in prompts")
    print("   • Hierarchical resource access patterns")
    print("   • Cross-service resource correlation")
    print()
    print("🧠 Intelligent Content Generation:")
    print("   • Context-aware email composition")
    print("   • Data-driven template customization")
    print("   • Professional styling with dynamic content")
    print("   • Automated insight generation")
    print()
    print("📊 Advanced Analytics Capabilities:")
    print("   • Real-time configuration analysis")
    print("   • Performance optimization recommendations")
    print("   • Trend monitoring and reporting")
    print("   • Executive dashboard generation")
    print()
    print("🚀 Production-Ready Features:")
    print("   • Error handling and graceful fallbacks")
    print("   • Scalable architecture design")
    print("   • Cross-platform compatibility")
    print("   • Integration with existing workflows")
    print()
    
    logger.info("✅ Enhanced Gmail Prompts Demo Complete!")
    return True

if __name__ == "__main__":
    """
    Run the demonstration when script is executed directly.
    """
    try:
        asyncio.run(demonstrate_dynamic_gmail_prompts())
        print("\n🎯 Demo completed successfully!")
        print("📚 Check the prompts/gmail_prompts_main.py for setup instructions")
        print("🔗 Explore service_list_resources.py for resource integration details")
        
    except Exception as e:
        logger.error(f"❌ Demo failed: {e}")
        print(f"\n💥 Demo error: {e}")
        print("🔧 Check your FastMCP2 setup and resource configuration")