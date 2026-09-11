import React from 'react';
import { ShieldCheck, GitBranch, Layers, PieChart, DollarSign, Users, FileText, ExternalLink, Code } from 'lucide-react';

interface NavbarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  proposalCount: number;
  capitalCallPendingCount: number;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  setActiveTab,
  proposalCount,
  capitalCallPendingCount,
}) => {
  const tabs = [
    { id: 'pipeline', label: 'Pipeline Intake', icon: Layers },
    { id: 'captable', label: 'Cap Table & Proposals', icon: PieChart, badge: proposalCount > 0 ? proposalCount : undefined },
    { id: 'capitalcalls', label: 'Capital Calls', icon: DollarSign, badge: capitalCallPendingCount > 0 ? capitalCallPendingCount : undefined },
    { id: 'investors', label: 'Cross-Fund Investors', icon: Users },
    { id: 'ledger', label: 'Audit Ledger', icon: ShieldCheck },
    { id: 'repo', label: 'Repository & Docs', icon: Code },
    { id: 'original', label: 'Raw Static UI', icon: ExternalLink },
  ];

  return (
    <nav className="sticky top-0 z-50 bg-[#0B1B23]/95 backdrop-blur-md border-b border-[rgba(237,230,216,0.14)]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3 flex flex-wrap items-center justify-between gap-4">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg overflow-hidden border border-purple-500/30 flex items-center justify-center shadow-xs">
            <img
              src="/flowgate-logo.png"
              alt="Flowgate"
              className="w-full h-full object-cover"
              referrerPolicy="no-referrer"
            />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-sm tracking-wider uppercase text-[#B9AD97]">
                Flowgate <strong className="text-[#E4C878]">/// Operations</strong>
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full border border-[#4C7A6E] text-[#6FA093] bg-[#4C7A6E]/10">
                v0.1.0 Shipped
              </span>
            </div>
            <div className="text-[11px] text-[#B9AD97]/70 flex items-center gap-1.5 mt-0.5">
              <span>titouhalloub/flowgate</span>
              <span>•</span>
              <span className="text-[#6FA093] flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-[#6FA093] animate-pulse"></span>
                Local Engine Live
              </span>
            </div>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="flex items-center gap-1 overflow-x-auto pb-1 sm:pb-0">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                id={`tab-${tab.id}`}
                onClick={() => setActiveTab(tab.id)}
                className={`relative flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-mono transition-colors whitespace-nowrap ${
                  isActive
                    ? 'bg-[#12262F] text-[#EDE6D8] border border-[#C9A24B]/50 shadow-sm'
                    : 'text-[#B9AD97] hover:text-[#EDE6D8] hover:bg-[#12262F]/50 border border-transparent'
                }`}
              >
                <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-[#E4C878]' : 'text-[#B9AD97]'}`} />
                <span>{tab.label}</span>
                {tab.badge !== undefined && (
                  <span className="ml-1 px-1.5 py-0.2 rounded-full bg-[#D98E3B] text-[#0B1B23] text-[10px] font-bold">
                    {tab.badge}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* GitHub link button */}
        <div className="hidden lg:flex items-center gap-2">
          <a
            href="https://github.com/titouhalloub/flowgate"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-mono text-[#B9AD97] hover:text-[#E4C878] border border-[rgba(237,230,216,0.15)] hover:border-[#C9A24B]/60 transition-colors"
          >
            <GitBranch className="w-3.5 h-3.5" />
            <span>GitHub Repo</span>
          </a>
        </div>
      </div>
    </nav>
  );
};
