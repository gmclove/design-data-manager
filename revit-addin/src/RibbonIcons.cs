using System;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;

namespace DesignDataManager.Revit
{
    /// <summary>
    /// The ribbon buttons' icons, drawn in code so the add-in ships no image files. Each is drawn on
    /// a 16-unit grid and scaled: 16 px for the small image, 32 px for the large one. Lines sit on
    /// half units so they land on whole pixels at both sizes.
    /// </summary>
    internal static class RibbonIcons
    {
        private static readonly Color Ink = Color.FromRgb(0x1B, 0x3A, 0x5C);
        private static readonly Color Blue = Color.FromRgb(0x2B, 0x6C, 0xB0);
        private static readonly Color LightBlue = Color.FromRgb(0x7F, 0xB2, 0xE5);
        private static readonly Color Rule = Color.FromRgb(0x9A, 0xA5, 0xB1);

        /// <summary>A schedule: a table with a blue header row.</summary>
        public static BitmapSource Schedule(int size) => Render(size, DrawSchedule);

        /// <summary>The database: a cylinder.</summary>
        public static BitmapSource Database(int size) => Render(size, DrawDatabase);

        /// <summary>A Linker ID: a tag label with a hash mark.</summary>
        public static BitmapSource LinkerId(int size) => Render(size, DrawLinkerId);

        /// <summary>Link Elements: two chain links.</summary>
        public static BitmapSource Link(int size) => Render(size, DrawLink);

        /// <summary>Sync Linked Elements: a filled box copying to an outlined one.</summary>
        public static BitmapSource SyncLinked(int size) => Render(size, DrawSyncLinked);

        private static BitmapSource Render(int size, Action<DrawingContext> draw)
        {
            var visual = new DrawingVisual();
            using (DrawingContext dc = visual.RenderOpen())
            {
                dc.PushTransform(new ScaleTransform(size / 16.0, size / 16.0));
                draw(dc);
                dc.Pop();
            }
            var bitmap = new RenderTargetBitmap(size, size, 96, 96, PixelFormats.Pbgra32);
            bitmap.Render(visual);
            bitmap.Freeze();
            return bitmap;
        }

        private static Pen Line(Color color) => new Pen(new SolidColorBrush(color), 1.0);

        private static void DrawSchedule(DrawingContext dc)
        {
            var table = new Rect(new Point(1.5, 2.5), new Point(14.5, 13.5));
            dc.DrawRectangle(Brushes.White, null, table);
            dc.DrawRectangle(new SolidColorBrush(Blue), null, new Rect(new Point(1.5, 2.5), new Point(14.5, 5.5)));
            Pen rule = Line(Rule);
            foreach (double y in new[] { 7.5, 9.5, 11.5 })
            {
                dc.DrawLine(rule, new Point(1.5, y), new Point(14.5, y));
            }
            foreach (double x in new[] { 6.5, 10.5 })
            {
                dc.DrawLine(rule, new Point(x, 5.5), new Point(x, 13.5));
            }
            dc.DrawRectangle(null, Line(Ink), table);
        }

        private static void DrawDatabase(DrawingContext dc)
        {
            // The body: sides and the rounded bottom.
            var body = new PathGeometry();
            var outline = new PathFigure { StartPoint = new Point(2.5, 4), IsClosed = true };
            outline.Segments.Add(new LineSegment(new Point(2.5, 12), true));
            outline.Segments.Add(new ArcSegment(new Point(13.5, 12), new Size(5.5, 2), 0, false, SweepDirection.Counterclockwise, true));
            outline.Segments.Add(new LineSegment(new Point(13.5, 4), true));
            body.Figures.Add(outline);
            dc.DrawGeometry(new SolidColorBrush(Blue), Line(Ink), body);

            // Bands across the body.
            Pen band = Line(LightBlue);
            foreach (double y in new[] { 6.75, 9.5 })
            {
                var arc = new PathGeometry();
                var figure = new PathFigure { StartPoint = new Point(3, y) };
                figure.Segments.Add(new ArcSegment(new Point(13, y), new Size(5, 2), 0, false, SweepDirection.Counterclockwise, true));
                arc.Figures.Add(figure);
                dc.DrawGeometry(null, band, arc);
            }

            // The top.
            dc.DrawEllipse(new SolidColorBrush(LightBlue), Line(Ink), new Point(8, 4), 5.5, 2);
        }

        private static void DrawLinkerId(DrawingContext dc)
        {
            // A tag: a box with a pointed left end and a hole.
            var tag = new PathGeometry();
            var outline = new PathFigure { StartPoint = new Point(1.5, 8), IsClosed = true };
            outline.Segments.Add(new LineSegment(new Point(5.5, 3.5), true));
            outline.Segments.Add(new LineSegment(new Point(14.5, 3.5), true));
            outline.Segments.Add(new LineSegment(new Point(14.5, 12.5), true));
            outline.Segments.Add(new LineSegment(new Point(5.5, 12.5), true));
            tag.Figures.Add(outline);
            dc.DrawGeometry(new SolidColorBrush(Blue), Line(Ink), tag);
            dc.DrawEllipse(Brushes.White, null, new Point(5, 8), 1, 1);
            // "#" in white.
            var white = new Pen(Brushes.White, 1.0);
            dc.DrawLine(white, new Point(9.5, 5.5), new Point(8.5, 10.5));
            dc.DrawLine(white, new Point(12, 5.5), new Point(11, 10.5));
            dc.DrawLine(white, new Point(7.5, 7.5), new Point(13, 7.5));
            dc.DrawLine(white, new Point(7, 9.5), new Point(12.5, 9.5));
        }

        private static void DrawLink(DrawingContext dc)
        {
            var thick = new Pen(new SolidColorBrush(Blue), 2.0);
            var ink = new Pen(new SolidColorBrush(Ink), 2.0);
            var left = new RectangleGeometry(new Rect(new Point(1.5, 5.5), new Point(9.5, 10.5)), 2.5, 2.5);
            var right = new RectangleGeometry(new Rect(new Point(6.5, 5.5), new Point(14.5, 10.5)), 2.5, 2.5);
            left.Transform = new RotateTransform(-35, 5.5, 8);
            right.Transform = new RotateTransform(-35, 10.5, 8);
            dc.DrawGeometry(null, ink, left);
            dc.DrawGeometry(null, thick, right);
        }

        private static void DrawSyncLinked(DrawingContext dc)
        {
            // The primary (filled), an arrow, and two linked copies (outlined).
            dc.DrawRectangle(new SolidColorBrush(Blue), Line(Ink), new Rect(new Point(1.5, 5.5), new Point(6.5, 10.5)));
            Pen arrow = Line(Ink);
            dc.DrawLine(arrow, new Point(7.5, 8), new Point(10, 8));
            dc.DrawLine(arrow, new Point(8.5, 6.5), new Point(10, 8));
            dc.DrawLine(arrow, new Point(8.5, 9.5), new Point(10, 8));
            dc.DrawRectangle(Brushes.White, Line(Ink), new Rect(new Point(11.5, 2.5), new Point(14.5, 6.5)));
            dc.DrawRectangle(Brushes.White, Line(Ink), new Rect(new Point(11.5, 9.5), new Point(14.5, 13.5)));
            dc.DrawRectangle(new SolidColorBrush(LightBlue), null, new Rect(new Point(12.5, 3.5), new Point(13.5, 5.5)));
            dc.DrawRectangle(new SolidColorBrush(LightBlue), null, new Rect(new Point(12.5, 10.5), new Point(13.5, 12.5)));
        }
    }
}
