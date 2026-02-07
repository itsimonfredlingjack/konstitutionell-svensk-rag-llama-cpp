import React, { useRef, useEffect, useCallback } from "react";
import { useAppStore } from "../../stores/useAppStore";
import { ChatMessage } from "./ChatMessage";
import { ChatInput } from "./ChatInput";

export const ChatView: React.FC = () => {
    const queries = useAppStore((s) => s.queries);
    const isSearching = useAppStore((s) => s.isSearching);
    const scrollRef = useRef<HTMLDivElement>(null);
    const lastScrollHeightRef = useRef(0);

    // Scroll to bottom function - uses instant scroll for reliability
    const scrollToBottom = useCallback((behavior: ScrollBehavior = "smooth") => {
        if (scrollRef.current) {
            const container = scrollRef.current;
            // Only scroll if content height has changed or we're near bottom
            const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 200;
            const heightChanged = container.scrollHeight !== lastScrollHeightRef.current;

            if (isNearBottom || heightChanged) {
                container.scrollTo({
                    top: container.scrollHeight,
                    behavior,
                });
                lastScrollHeightRef.current = container.scrollHeight;
            }
        }
    }, []);

    // Force scroll on new queries - immediate
    useEffect(() => {
        if (queries.length > 0) {
            // Immediate scroll
            scrollToBottom("instant");
            // And again after render settles
            const t1 = setTimeout(() => scrollToBottom("instant"), 50);
            const t2 = setTimeout(() => scrollToBottom("smooth"), 200);
            return () => {
                clearTimeout(t1);
                clearTimeout(t2);
            };
        }
    }, [queries.length, scrollToBottom]);

    // Scroll during streaming and on completion
    const lastQuery = queries[queries.length - 1];
    const answerLength = lastQuery?.answer?.length ?? 0;
    const searchStage = lastQuery?.searchStage ?? "";
    const pipelineStage = lastQuery?.pipelineStage ?? "";

    useEffect(() => {
        // Scroll whenever answer grows or pipeline progresses
        if (answerLength > 0 || searchStage === "complete" || isSearching) {
            const timer = setTimeout(() => scrollToBottom("smooth"), 50);
            return () => clearTimeout(timer);
        }
    }, [answerLength, searchStage, pipelineStage, isSearching, scrollToBottom]);

    // Also scroll on any pipeline stage change
    useEffect(() => {
        if (pipelineStage && pipelineStage !== "idle") {
            scrollToBottom("smooth");
        }
    }, [pipelineStage, scrollToBottom]);

    return (
        <div className="flex flex-col h-full min-h-0">
            {/* Scrollable chat history */}
            <div
                ref={scrollRef}
                className="flex-1 overflow-y-auto overflow-x-hidden custom-scrollbar px-4 py-6"
            >
                {queries.length === 0 ? (
                    <div className="flex items-center justify-center h-full">
                        <div className="text-center text-stone-500">
                            <p className="text-lg mb-2">Ställ en fråga för att börja</p>
                            <p className="text-sm font-mono opacity-60">
                                Välj läge (V/S/C) och skriv din fråga nedan
                            </p>
                        </div>
                    </div>
                ) : (
                    <div className="space-y-8 pb-4">
                        {queries.map((q) => (
                            <ChatMessage key={q.id} queryResult={q} />
                        ))}
                    </div>
                )}
            </div>

            {/* Fixed input at bottom */}
            <ChatInput />
        </div>
    );
};
