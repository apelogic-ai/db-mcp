import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export default function QueryPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Query Console</h1>
        <p className="text-gray-400 mt-1">Natural language to SQL</p>
      </div>

      <Card className="bg-gray-900 border-gray-800">
        <CardHeader>
          <CardTitle className="text-white flex items-center gap-2">
            Natural Language Query
            <Badge variant="secondary" className="bg-gray-800 text-gray-300">
              Coming Soon
            </Badge>
          </CardTitle>
          <CardDescription className="text-gray-400">
            Ask questions in natural language and get SQL queries generated
            automatically. Review, edit, and execute queries directly.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-gray-500 text-sm">
            Connect to a database to start querying with natural language.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
