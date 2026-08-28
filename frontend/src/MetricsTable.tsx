export interface Metric {
    symbol: string;
    annualized_return: number;
    annualized_volatility: number;
}

interface MetricsTableProps {
    metrics: Metric[];
}

function MetricsTable({ metrics }: MetricsTableProps) {
    return (
        <table>
            <thead>
                <tr>
                    <th>Symbol</th>
                    <th>Return</th>
                    <th>Volatility</th>
                </tr>
            </thead>
            <tbody>
                {metrics.length === 0 ? (
                    <tr><td colSpan={3}>No historical data available</td></tr>
                ) : (
                    metrics.map((m) => (
                        <tr key={m.symbol}>
                            <td>{m.symbol}</td>
                            <td style={{ color: m.annualized_return < 0 ? "#e57373" : undefined }}>
                                {(m.annualized_return * 100).toFixed(2)}%
                            </td>
                            <td>{(m.annualized_volatility * 100).toFixed(2)}%</td>
                        </tr>
                    ))
                )}
            </tbody>
        </table>
    );
}

export default MetricsTable;