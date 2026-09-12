import React from 'react';
import {
  Activity,
  LayoutGrid,
  BarChart3,
  Building2,
  Users,
  Coins,
  Settings,
  ShieldCheck,
  Code,
} from 'lucide-react';

interface ModernSidebarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  proposalCount: number;
  capitalCallPendingCount: number;
}

export const ModernSidebar: React.FC<ModernSidebarProps> = ({
  activeTab,
  setActiveTab,
  proposalCount,
  capitalCallPendingCount,
}) => {
  const navItems = [
    {
      id: 'dashboard',
      label: 'Cap Table Dashboard',
      icon: Activity,
    },
    {
      id: 'pipeline',
      label: 'Document Intake & Compliance',
      icon: LayoutGrid,
    },
    {
      id: 'captable',
      label: 'Cap Table Registry & Proposals',
      icon: Building2,
      badge: proposalCount > 0 ? proposalCount : undefined,
    },
    {
      id: 'capitalcalls',
      label: 'Capital Calls & Drawdowns',
      icon: Coins,
      badge: capitalCallPendingCount > 0 ? capitalCallPendingCount : undefined,
    },
    {
      id: 'investors',
      label: 'Cross-Fund Investors',
      icon: Users,
    },
    {
      id: 'ledger',
      label: 'Unified Audit Ledger',
      icon: ShieldCheck,
    },
    {
      id: 'repo',
      label: 'Repository Code & Docs',
      icon: Code,
    },
  ];

  return (
    <aside className="w-16 sm:w-20 bg-white border-r border-gray-100 flex flex-col items-center py-6 select-none flex-shrink-0 min-h-screen">
      {/* Top Hexagon Brand Icon */}
      <div
        onClick={() => setActiveTab('dashboard')}
        className="w-10 h-10 rounded-xl overflow-hidden shadow-md shadow-purple-500/20 cursor-pointer hover:scale-105 transition-transform mb-8 border border-purple-200/50"
        title="Flowgate"
      >
        <img
          src={`${import.meta.env.BASE_URL}flowgate-logo.png`}
          alt="Flowgate"
          className="w-full h-full object-cover"
          referrerPolicy="no-referrer"
        />
      </div>

      {/* Navigation Icons Stack */}
      <div className="flex flex-col items-center gap-3.5 flex-1">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              id={`nav-btn-${item.id}`}
              onClick={() => setActiveTab(item.id)}
              title={item.label}
              className={`relative p-3 rounded-xl transition-all ${
                isActive
                  ? 'bg-[#F0ECFE] text-[#7048E8] shadow-xs'
                  : 'text-gray-400 hover:text-gray-600 hover:bg-gray-50'
              }`}
            >
              <Icon className="w-5 h-5 stroke-[2.2]" />

              {item.badge !== undefined && (
                <span className="absolute top-1.5 right-1.5 w-4 h-4 bg-[#FF6B2C] text-white text-[9px] font-bold rounded-full flex items-center justify-center">
                  {item.badge}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Bottom Settings Icon */}
      <button
        onClick={() => setActiveTab('repo')}
        title="Settings & Repository"
        className="p-3 text-gray-400 hover:text-gray-600 hover:bg-gray-50 rounded-xl transition-all"
      >
        <Settings className="w-5 h-5 stroke-[2.2]" />
      </button>
    </aside>
  );
};
