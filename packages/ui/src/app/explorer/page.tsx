import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export default function ExplorerPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Query Explorer</h1>
        <p className="text-gray-400 mt-1">View query history and traces</p>
      </div>

      <Card className="bg-gray-900 border-gray-800">
        <CardHeader>
          <CardTitle className="text-white flex items-center gap-2">
            Query History
            <Badge variant="secondary" className="bg-gray-800 text-gray-300">
              Coming Soon
            </Badge>
          </CardTitle>
          <CardDescription className="text-gray-400">
            Browse past queries, view execution traces, analyze performance, and
            debug query generation.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-gray-500 text-sm">
            Query history will appear here once you start executing queries.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
