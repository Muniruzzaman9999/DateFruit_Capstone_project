import { Link } from "react-router-dom";
import { CameraIcon, SparklesIcon, StoreIcon, TagIcon, TrophyIcon } from "../components/icons";
import { Card, buttonClass, secondaryButtonClass } from "../components/ui";
import { useAuth } from "../context/useAuth";

const STEPS = [
  {
    icon: CameraIcon,
    title: "Upload Photo",
    body: "Select a photo or capture dates using your phone camera.",
  },
  {
    icon: SparklesIcon,
    title: "AI Variety Detection",
    body: "Trained neural network identifies 9 date varieties with instant confidence scores.",
  },
  {
    icon: TagIcon,
    title: "Confirm & Price",
    body: "Confirm AI prediction or select custom variety, enter price & unit details.",
  },
  {
    icon: StoreIcon,
    title: "Publish to Marketplace",
    body: "List your shop name, contact number, and location for immediate buyer visibility.",
  },
  {
    icon: TrophyIcon,
    title: "Price Comparison Index",
    body: "Compare per-gram prices across all sellers to discover the cheapest market offers.",
  },
];

export default function HomePage() {
  const { isLoggedIn } = useAuth();

  return (
    <div className="space-y-12 py-4">
      {/* Hero Section */}
      <section className="text-center max-w-3xl mx-auto space-y-6">
        <div className="inline-flex items-center gap-2 rounded-full bg-amber-100/90 border border-amber-300/60 px-4 py-1.5 text-xs font-bold text-amber-900 shadow-xs">
          <SparklesIcon className="w-4 h-4 text-amber-700" />
          Real-Time AI Date Fruit Classification &amp; Price Comparison
        </div>

        <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight text-stone-900 leading-tight font-heading">
          Instant AI Date Variety Recognition &amp; Market Price Index
        </h1>

        <p className="text-base sm:text-lg text-stone-600 font-normal leading-relaxed">
          Upload any date fruit photo to identify variety, check per-gram pricing across shops, and publish live listings for date fruit buyers and sellers.
        </p>

        <div className="flex flex-wrap items-center justify-center gap-3 pt-2">
          {isLoggedIn ? (
            <Link to="/app" className={buttonClass + " px-8 py-3 text-base shadow-lg"}>
              <StoreIcon className="w-5 h-5" />
              Open Marketplace
            </Link>
          ) : (
            <>
              <Link to="/register" className={buttonClass + " px-8 py-3 text-base shadow-lg"}>
                Get Started Free
              </Link>
              <Link to="/login" className={secondaryButtonClass + " px-8 py-3 text-base"}>
                Log In to Account
              </Link>
            </>
          )}
        </div>
      </section>

      {/* Feature Step Cards */}
      <section>
        <div className="text-center mb-8">
          <h2 className="text-2xl font-bold text-stone-900">How It Works</h2>
          <p className="text-xs text-stone-500 mt-1">Five seamless steps from photo upload to price comparison</p>
        </div>

        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {STEPS.map((step, index) => {
            const Icon = step.icon;
            return (
              <Card key={step.title} className="relative group border-stone-200/80 hover:border-amber-400">
                <div className="flex items-start gap-4">
                  <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-amber-100/80 text-amber-700 group-hover:bg-amber-600 group-hover:text-white transition-colors duration-200 shadow-inner">
                    <Icon className="w-6 h-6" />
                  </div>
                  <div>
                    <span className="text-xs font-bold text-amber-600">Step {index + 1}</span>
                    <h3 className="font-bold text-stone-900 text-base">{step.title}</h3>
                    <p className="mt-1 text-xs text-stone-600 leading-relaxed">{step.body}</p>
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      </section>

      {/* Model Capabilities Info Card */}
      <Card className="border-amber-200/80 bg-gradient-to-r from-white via-amber-50/20 to-emerald-50/20">
        <div className="flex items-center gap-2 mb-2">
          <SparklesIcon className="w-5 h-5 text-amber-600" />
          <h3 className="text-lg font-bold text-stone-900">Recognized Date Varieties</h3>
        </div>
        <p className="text-xs text-stone-600 leading-relaxed">
          Our deep neural network is trained to classify 9 primary date fruit varieties: <strong className="text-stone-900">Ajwa, Galaxy, Medjool, Meneifi, Nabtat Ali, Rutab, Shaishe, Sokari, and Sugaey</strong>. You can also publish custom user-added categories manually.
        </p>
      </Card>
    </div>
  );
}
