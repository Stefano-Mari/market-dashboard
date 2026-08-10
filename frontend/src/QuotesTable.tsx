export interface Quote {
    symbol: string;
    bid_price: number;
    ask_price: number;
    spread: number;
    ts: string;
    age_seconds: number;
    is_stale: boolean;
}

interface QuotesTableProps {
    quotes: Quote[];
}

function QuotesTable({ quotes }: QuotesTableProps) {
    return(
        <table>
            <thead>
                <tr>
                    <th>Symbol</th>
                    <th>Bid</th>
                    <th>Ask</th>
                    <th>Spread</th>
                    <th>Age</th>
                </tr>
            </thead>
            <tbody>
                {quotes.map((q) => (
                    <tr key={q.symbol}>
                        <td>{q.symbol}</td>
                        <td>{q.bid_price.toFixed(2)}</td>
                        <td>{q.ask_price.toFixed(2)}</td>
                        <td>{q.spread.toFixed(2)}</td>
                        <td>
                            {Math.round(q.age_seconds)}s 
                            {q.is_stale && <span style={{color: "#e57373"}}> stale</span>}
                        </td>
                    </tr>
                ))}
            </tbody>
        </table>
    );
}

export default QuotesTable;