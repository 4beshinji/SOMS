import { MessageCircle } from 'lucide-react';
import { motion } from 'framer-motion';

interface Props {
  onClick: () => void;
}

export default function ChatButton({ onClick }: Props) {
  return (
    <motion.button
      onClick={onClick}
      className="fixed bottom-6 right-6 z-40 w-14 h-14 rounded-full
                 bg-[var(--primary-600)] text-white shadow-lg
                 flex items-center justify-center
                 hover:bg-[var(--primary-700)] active:scale-95
                 transition-colors cursor-pointer"
      whileHover={{ scale: 1.05 }}
      whileTap={{ scale: 0.95 }}
      aria-label="チャットを開く"
    >
      <MessageCircle className="w-6 h-6" />
    </motion.button>
  );
}
