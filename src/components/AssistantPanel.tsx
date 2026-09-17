import React, { useRef, useState, useEffect } from 'react';
import { MessageCircle, X, Send, Loader2 } from 'lucide-react';
import { askAssistant } from '../services/api';

interface AssistantMessage {
  role: 'user' | 'assistant';
  text: string;
  sources?: string[];
}

interface AssistantPanelProps {
  issuerName?: string;
}

const EXAMPLE_QUESTIONS = [
  'What is a convertible?',
  'Why might a document be routed to human review?',
  'How does the 409A gate work?',
];

export const AssistantPanel: React.FC<AssistantPanelProps> = ({ issuerName }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [input, setInput] = useState('');
  const [isPending, setIsPending] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isPending]);

  const handleAsk = async (question: string) => {
    const trimmed = question.trim();
    if (!trimmed || isPending) return;

    setMessages((prev) => [...prev, { role: 'user', text: trimmed }]);
    setInput('');
    setIsPending(true);

    try {
      const result = await askAssistant(trimmed, issuerName);
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', text: result.answer, sources: result.sources },
      ]);
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          text: err?.message ?? 'Something went wrong. Please try again.',
        },
      ]);
    } finally {
      setIsPending(false);
    }
  };

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-4 right-4 z-40 w-12 h-12 rounded-full bg-[#7048E8] text-white flex items-center justify-center shadow-lg hover:bg-[#5C38D1] transition-colors"
        aria-label="Open assistant"
      >
        <MessageCircle className="w-5 h-5" />
      </button>
    );
  }

  return (
    <div className="fixed bottom-4 right-4 z-40 w-96 h-[600px] bg-white rounded-2xl shadow-xl border border-gray-200 flex flex-col">
      <div className="flex items-center justify-between p-4 border-b border-gray-100">
        <div className="flex items-center gap-2">
          <MessageCircle className="w-4 h-4 text-[#7048E8]" />
          <span className="text-sm font-bold text-gray-900">Flowgate Assistant</span>
        </div>
        <button
          onClick={() => setIsOpen(false)}
          className="text-gray-400 hover:text-gray-700"
          aria-label="Close assistant"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.length === 0 && (
          <div className="space-y-3">
            <p className="text-xs text-gray-500">
              Ask me anything about how Flowgate works. I answer from the
              app&apos;s own documentation.
            </p>
            <div className="space-y-1.5">
              {EXAMPLE_QUESTIONS.map((q) => (
                <button
                  key={q}
                  onClick={() => handleAsk(q)}
                  className="w-full text-left text-xs px-3 py-2 rounded-lg bg-gray-50 hover:bg-[#EBE7FD] text-gray-700 border border-gray-100"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div
            key={i}
            className={`text-xs ${
              m.role === 'user'
                ? 'ml-8 bg-[#EBE7FD] text-[#2A1B6B] rounded-lg p-2.5'
                : 'mr-8 bg-gray-50 text-gray-800 rounded-lg p-2.5'
            }`}
          >
            <div className="whitespace-pre-wrap">{m.text}</div>
            {m.sources && m.sources.length > 0 && (
              <div className="mt-1.5 pt-1.5 border-t border-gray-200 text-[10px] text-gray-500">
                Sources: {m.sources.join(', ')}
              </div>
            )}
          </div>
        ))}

        {isPending && (
          <div className="flex items-center gap-2 text-xs text-gray-400">
            <Loader2 className="w-3 h-3 animate-spin" />
            Thinking...
          </div>
        )}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          handleAsk(input);
        }}
        className="p-3 border-t border-gray-100 flex items-center gap-2"
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question..."
          className="flex-1 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 text-xs outline-none focus:border-[#7048E8]"
          disabled={isPending}
        />
        <button
          type="submit"
          disabled={isPending || !input.trim()}
          className="w-8 h-8 rounded-lg bg-[#7048E8] text-white flex items-center justify-center hover:bg-[#5C38D1] disabled:opacity-40"
          aria-label="Send"
        >
          <Send className="w-3.5 h-3.5" />
        </button>
      </form>
    </div>
  );
};
