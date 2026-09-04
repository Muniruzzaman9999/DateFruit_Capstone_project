import { Link } from "react-router-dom";

import { Card, secondaryButtonClass } from "../components/ui";

export default function NotFoundPage() {
  return (
    <div className="mx-auto max-w-md text-center">
      <Card>
        <h1 className="text-xl font-semibold text-stone-900">Page not found</h1>
        <p className="mt-2 text-sm text-stone-600">
          That address does not exist in this application.
        </p>
        <Link to="/" className={`${secondaryButtonClass} mt-4`}>
          Back to the start
        </Link>
      </Card>
    </div>
  );
}
