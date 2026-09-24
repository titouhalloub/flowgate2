import React, { useEffect, useState } from 'react';
import {
  Activity,
  LayoutGrid,
  Building2,
  Users,
  Coins,
  Settings,
  ShieldCheck,
  Code,
  BookOpen,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { UserButton } from '@clerk/clerk-react';

interface ModernSidebarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  proposalCount: number;
  capitalCallPendingCount: number;
}

type NavItem = {
  id: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: number;
  href?: string;
};

const STORAGE_KEY = 'flowgate.sidebar.expanded';

export const ModernSidebar: React.FC<ModernSidebarProps> = ({
  activeTab,
  setActiveTab,
  proposalCount,
  capitalCallPendingCount,
}) => {
  const [expanded, setExpanded] = useState<boolean>(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) === 'true';
    } catch {
      return false;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, String(expanded));
    } catch {
      // localStorage may be unavailable (private mode); ignore
    }
  }, [expanded]);

  const navItems: NavItem[] = [
    { id: 'dashboard', label: 'Cap Table Dashboard', icon: Activity },
    { id: 'pipeline', label: 'Document Intake & Compliance', icon: LayoutGrid },
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
    { id: 'investors', label: 'Cross-Fund Investors', icon: Users },
    { id: 'ledger', label: 'Unified Audit Ledger', icon: ShieldCheck },
    { id: 'compliance', label: 'Compliance Rules', icon: ShieldCheck },
    { id: 'repo', label: 'Repository Code & Docs', icon: Code },
    { id: 'api-docs', label: 'API Documentation', icon: BookOpen, href: '/api-docs' },
  ];

  const asideWidth = expanded ? 'w-64' : 'w-16 sm:w-20';

  return (
    <aside
      className={`${asideWidth} bg-white border-r border-gray-100 flex flex-col ${expanded ? 'items-stretch px-3' : 'items-center'} py-6 select-none flex-shrink-0 min-h-screen transition-all duration-200`}
    >
      {/* Brand mark */}
      <div className={expanded ? 'flex items-center justify-between mb-6 px-1' : 'mb-6'}>
        <div
          onClick={() => setActiveTab('dashboard')}
          className="w-10 h-10 rounded-xl overflow-hidden shadow-md shadow-purple-500/20 cursor-pointer hover:scale-105 transition-transform border border-purple-200/50"
          title="Flowgate"
        >
          <img
            src={`${import.meta.env.BASE_URL}flowgate-logo.png`}
            alt="Flowgate"
            className="w-full h-full object-cover"
            referrerPolicy="no-referrer"
          />
        </div>
        {expanded && (
          <button
            onClick={() => setExpanded(false)}
            title="Collapse sidebar"
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-50 transition-colors cursor-pointer"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Collapsed-mode expand toggle */}
      {!expanded && (
        <button
          onClick={() => setExpanded(true)}
          title="Expand sidebar"
          className="mb-4 p-2 rounded-lg text-gray-400 hover:text-[#7048E8] hover:bg-[#F4F6FC] transition-colors cursor-pointer"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
      )}

      {/* Navigation items */}
      <div className={`flex flex-col ${expanded ? '' : 'items-center'} gap-1.5 flex-1`}>
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = !item.href && activeTab === item.id;

          if (item.href) {
            return (
              <a
                key={item.id}
                href={item.href}
                target="_blank"
                rel="noopener noreferrer"
                title={item.label}
                className={
                  expanded
                    ? 'flex items-center gap-3 px-3 py-2.5 rounded-xl text-gray-500 hover:text-[#7048E8] hover:bg-[#F4F6FC] transition-colors'
                    : 'relative p-3 rounded-xl text-gray-400 hover:text-[#7048E8] hover:bg-[#F4F6FC] transition-all'
                }
              >
                <Icon className="w-5 h-5 stroke-[2.2] flex-shrink-0" />
                {expanded && (
                  <span className="text-sm font-semibold truncate min-w-0">
                    {item.label}
                  </span>
                )}
              </a>
            );
          }

          return (
            <button
              key={item.id}
              id={`nav-btn-${item.id}`}
              onClick={() => setActiveTab(item.id)}
              title={item.label}
              className={
                expanded
                  ? `flex items-center gap-3 px-3 py-2.5 rounded-xl transition-colors text-left w-full cursor-pointer ${
                      isActive
                        ? 'bg-[#F0ECFE] text-[#7048E8]'
                        : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
                    }`
                  : `relative p-3 rounded-xl transition-all cursor-pointer ${
                      isActive
                        ? 'bg-[#F0ECFE] text-[#7048E8] shadow-xs'
                        : 'text-gray-400 hover:text-gray-600 hover:bg-gray-50'
                    }`
              }
            >
              <Icon className="w-5 h-5 stroke-[2.2] flex-shrink-0" />
              {expanded && (
                <span className="text-sm font-semibold truncate min-w-0 flex-1">
                  {item.label}
                </span>
              )}
              {item.badge !== undefined && (
                <span
                  className={
                    expanded
                      ? 'ml-auto w-5 h-5 bg-[#FF6B2C] text-white text-[10px] font-bold rounded-full flex items-center justify-center flex-shrink-0'
                      : 'absolute top-1.5 right-1.5 w-4 h-4 bg-[#FF6B2C] text-white text-[9px] font-bold rounded-full flex items-center justify-center'
                  }
                >
                  {item.badge}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Clerk UserButton */}
      <div className={`${expanded ? 'mb-3 px-1' : 'mb-4'} flex ${expanded ? 'items-center gap-3' : 'justify-center'}`}>
        <UserButton afterSignOutUrl="/" />
        {expanded && (
          <span className="text-sm font-semibold text-gray-500 truncate min-w-0">Account</span>
        )}
      </div>

      {/* Settings */}
      <button
        onClick={() => setActiveTab('repo')}
        title="Settings & Repository"
        className={
          expanded
            ? 'flex items-center gap-3 px-3 py-2.5 rounded-xl text-gray-400 hover:text-gray-600 hover:bg-gray-50 transition-colors cursor-pointer'
            : 'p-3 text-gray-400 hover:text-gray-600 hover:bg-gray-50 rounded-xl transition-all cursor-pointer'
        }
      >
        <Settings className="w-5 h-5 stroke-[2.2] flex-shrink-0" />
        {expanded && (
          <span className="text-sm font-semibold truncate min-w-0">
            Settings & Repository
          </span>
        )}
      </button>
    </aside>
  );
};
