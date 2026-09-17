import { redirect } from 'next/navigation';

/** The resident is the default audience, and / should not be a fourth
 *  place the shell is rendered. */
export default function Home() {
  redirect('/resident');
}
