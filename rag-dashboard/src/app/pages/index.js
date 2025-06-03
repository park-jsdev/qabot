import { useState } from "react";

export default function Home() {
  const [question, setQuestion] = useState("");
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);

  async function askQuestion(e) {
    e.preventDefault();
    setLoading(true);
    setHistory(h => [...h, { role: "user", text: question }]);
    setQuestion("");
    const res = await fetch("http://localhost:8000/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const data = await res.json();
    setHistory(h => [
      ...h,
      { role: "assistant", text: data.answer, sources: data.sources }
    ]);
    setLoading(false);
  }

  return (
    <div className="min-h-screen bg-gray-100 p-6">
      <div className="max-w-2xl mx-auto bg-white rounded-xl shadow-lg p-8">
        <h1 className="text-2xl font-bold mb-4">SOP Chatbot Dashboard</h1>
        <form onSubmit={askQuestion} className="flex gap-2 mb-6">
          <input
            type="text"
            value={question}
            onChange={e => setQuestion(e.target.value)}
            className="flex-1 border p-2 rounded"
            placeholder="Ask a question about your SOPs..."
            disabled={loading}
          />
          <button
            type="submit"
            className="bg-blue-600 text-white px-4 py-2 rounded"
            disabled={loading || !question}
          >
            {loading ? "Asking..." : "Ask"}
          </button>
        </form>
        <div className="space-y-4">
          {history.map((msg, i) => (
            <div key={i} className={msg.role === "user" ? "text-right" : ""}>
              <div className={`p-2 rounded ${msg.role === "user" ? "bg-blue-100 inline-block" : "bg-green-100"}`}>
                <strong>{msg.role === "user" ? "You:" : "Assistant:"}</strong> {msg.text}
                {msg.sources && (
                  <div className="text-xs text-gray-500 mt-1">
                    <span>Sources: {msg.sources}</span>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
      {/* Dashboard panel (stats/refresh) could go here */}
    </div>
  );
}
