# Copyright 2018 The Bazel Authors. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import tempfile
import unittest
from typing import Any, List, Optional

from python.runfiles import runfiles


class RunfilesTest(unittest.TestCase):
    """Unit tests for `rules_python.python.runfiles.Runfiles`."""

    def testRlocationArgumentValidation(self) -> None:
        r = runfiles.Create({"RUNFILES_DIR": "whatever"})
        assert r is not None  # mypy doesn't understand the unittest api.
        self.assertRaises(ValueError, lambda: r.Rlocation(None))  # type: ignore
        self.assertRaises(ValueError, lambda: r.Rlocation(""))
        self.assertRaises(TypeError, lambda: r.Rlocation(1))  # type: ignore
        self.assertRaisesRegex(
            ValueError, "is not normalized", lambda: r.Rlocation("../foo")
        )
        self.assertRaisesRegex(
            ValueError, "is not normalized", lambda: r.Rlocation("foo/..")
        )
        self.assertRaisesRegex(
            ValueError, "is not normalized", lambda: r.Rlocation("foo/../bar")
        )
        self.assertRaisesRegex(
            ValueError, "is not normalized", lambda: r.Rlocation("./foo")
        )
        self.assertRaisesRegex(
            ValueError, "is not normalized", lambda: r.Rlocation("foo/.")
        )
        self.assertRaisesRegex(
            ValueError, "is not normalized", lambda: r.Rlocation("foo/./bar")
        )
        self.assertRaisesRegex(
            ValueError, "is not normalized", lambda: r.Rlocation("//foobar")
        )
        self.assertRaisesRegex(
            ValueError, "is not normalized", lambda: r.Rlocation("foo//")
        )
        self.assertRaisesRegex(
            ValueError, "is not normalized", lambda: r.Rlocation("foo//bar")
        )
        self.assertRaisesRegex(
            ValueError,
            "is absolute without a drive letter",
            lambda: r.Rlocation("\\foo"),
        )

    def testCreatesManifestBasedRunfiles(self) -> None:
        with _MockFile(contents=["a/b c/d"]) as mf:
            r = runfiles.Create(
                {
                    "RUNFILES_MANIFEST_FILE": mf.Path(),
                    "RUNFILES_DIR": "ignored when RUNFILES_MANIFEST_FILE has a value",
                    "TEST_SRCDIR": "always ignored",
                }
            )
            assert r is not None  # mypy doesn't understand the unittest api.
            self.assertEqual(r.Rlocation("a/b"), "c/d")
            self.assertIsNone(r.Rlocation("foo"))

    def testManifestBasedRunfilesEnvVars(self) -> None:
        with _MockFile(name="MANIFEST") as mf:
            r = runfiles.Create(
                {
                    "RUNFILES_MANIFEST_FILE": mf.Path(),
                    "TEST_SRCDIR": "always ignored",
                }
            )
            assert r is not None  # mypy doesn't understand the unittest api.
            self.assertDictEqual(
                r.EnvVars(),
                {
                    "RUNFILES_MANIFEST_FILE": mf.Path(),
                    "RUNFILES_DIR": mf.Path()[: -len("/MANIFEST")],
                    "JAVA_RUNFILES": mf.Path()[: -len("/MANIFEST")],
                },
            )

        with _MockFile(name="foo.runfiles_manifest") as mf:
            r = runfiles.Create(
                {
                    "RUNFILES_MANIFEST_FILE": mf.Path(),
                    "TEST_SRCDIR": "always ignored",
                }
            )
            assert r is not None  # mypy doesn't understand the unittest api.
            self.assertDictEqual(
                r.EnvVars(),
                {
                    "RUNFILES_MANIFEST_FILE": mf.Path(),
                    "RUNFILES_DIR": (
                        mf.Path()[: -len("foo.runfiles_manifest")] + "foo.runfiles"
                    ),
                    "JAVA_RUNFILES": (
                        mf.Path()[: -len("foo.runfiles_manifest")] + "foo.runfiles"
                    ),
                },
            )

        with _MockFile(name="x_manifest") as mf:
            r = runfiles.Create(
                {
                    "RUNFILES_MANIFEST_FILE": mf.Path(),
                    "TEST_SRCDIR": "always ignored",
                }
            )
            assert r is not None  # mypy doesn't understand the unittest api.
            self.assertDictEqual(
                r.EnvVars(),
                {
                    "RUNFILES_MANIFEST_FILE": mf.Path(),
                    "RUNFILES_DIR": "",
                    "JAVA_RUNFILES": "",
                },
            )

    def testCreatesDirectoryBasedRunfiles(self) -> None:
        r = runfiles.Create(
            {
                "RUNFILES_DIR": "runfiles/dir",
                "TEST_SRCDIR": "always ignored",
            }
        )
        assert r is not None  # mypy doesn't understand the unittest api.
        self.assertEqual(r.Rlocation("a/b"), "runfiles/dir/a/b")
        self.assertEqual(r.Rlocation("foo"), "runfiles/dir/foo")

    def testDirectoryBasedRunfilesEnvVars(self) -> None:
        r = runfiles.Create(
            {
                "RUNFILES_DIR": "runfiles/dir",
                "TEST_SRCDIR": "always ignored",
            }
        )
        assert r is not None  # mypy doesn't understand the unittest api.
        self.assertDictEqual(
            r.EnvVars(),
            {
                "RUNFILES_DIR": "runfiles/dir",
                "JAVA_RUNFILES": "runfiles/dir",
            },
        )

    def testFailsToCreateManifestBasedBecauseManifestDoesNotExist(self) -> None:
        def _Run():
            runfiles.Create({"RUNFILES_MANIFEST_FILE": "non-existing path"})

        self.assertRaisesRegex(IOError, "non-existing path", _Run)

    def testFailsToCreateAnyRunfilesBecauseEnvvarsAreNotDefined(self) -> None:
        with _MockFile(contents=["a b"]) as mf:
            runfiles.Create(
                {
                    "RUNFILES_MANIFEST_FILE": mf.Path(),
                    "RUNFILES_DIR": "whatever",
                    "TEST_SRCDIR": "always ignored",
                }
            )
        runfiles.Create(
            {
                "RUNFILES_DIR": "whatever",
                "TEST_SRCDIR": "always ignored",
            }
        )
        self.assertIsNone(runfiles.Create({"TEST_SRCDIR": "always ignored"}))
        self.assertIsNone(runfiles.Create({"FOO": "bar"}))

    def testManifestBasedRlocation(self) -> None:
        with _MockFile(
            contents=[
                "Foo/runfile1 ",  # A trailing whitespace is always present in single entry lines.
                "Foo/runfile2 C:/Actual Path\\runfile2",
                "Foo/Bar/runfile3 D:\\the path\\run file 3.txt",
                "Foo/Bar/Dir E:\\Actual Path\\Directory",
                " Foo\\sBar\\bDir\\nNewline/runfile5 F:\\bActual Path\\bwith\\nnewline/runfile5",
            ]
        ) as mf:
            r = runfiles.CreateManifestBased(mf.Path())
            self.assertEqual(r.Rlocation("Foo/runfile1"), "Foo/runfile1")
            self.assertEqual(r.Rlocation("Foo/runfile2"), "C:/Actual Path\\runfile2")
            self.assertEqual(
                r.Rlocation("Foo/Bar/runfile3"), "D:\\the path\\run file 3.txt"
            )
            self.assertEqual(
                r.Rlocation("Foo/Bar/Dir/runfile4"),
                "E:\\Actual Path\\Directory/runfile4",
            )
            self.assertEqual(
                r.Rlocation("Foo/Bar/Dir/Deeply/Nested/runfile4"),
                "E:\\Actual Path\\Directory/Deeply/Nested/runfile4",
            )
            self.assertEqual(
                r.Rlocation("Foo Bar\\Dir\nNewline/runfile5"),
                "F:\\Actual Path\\with\nnewline/runfile5",
            )
            self.assertIsNone(r.Rlocation("unknown"))
            if RunfilesTest.IsWindows():
                self.assertEqual(r.Rlocation("c:/foo"), "c:/foo")
                self.assertEqual(r.Rlocation("c:\\foo"), "c:\\foo")
            else:
                self.assertEqual(r.Rlocation("/foo"), "/foo")

    def testManifestBasedRlocationWithRepoMappingFromMain(self) -> None:
        with _MockFile(
            contents=[
                ",config.json,config.json~1.2.3",
                ",my_module,_main",
                ",my_protobuf,protobuf~3.19.2",
                ",my_workspace,_main",
                "protobuf~3.19.2,config.json,config.json~1.2.3",
                "protobuf~3.19.2,protobuf,protobuf~3.19.2",
            ]
        ) as rm, _MockFile(
            contents=[
                "_repo_mapping " + rm.Path(),
                "config.json /etc/config.json",
                "protobuf~3.19.2/foo/runfile C:/Actual Path\\protobuf\\runfile",
                "_main/bar/runfile /the/path/./to/other//other runfile.txt",
                "protobuf~3.19.2/bar/dir E:\\Actual Path\\Directory",
            ],
        ) as mf:
            r = runfiles.CreateManifestBased(mf.Path())

            self.assertEqual(
                r.Rlocation("my_module/bar/runfile", ""),
                "/the/path/./to/other//other runfile.txt",
            )
            self.assertEqual(
                r.Rlocation("my_workspace/bar/runfile", ""),
                "/the/path/./to/other//other runfile.txt",
            )
            self.assertEqual(
                r.Rlocation("my_protobuf/foo/runfile", ""),
                "C:/Actual Path\\protobuf\\runfile",
            )
            self.assertEqual(
                r.Rlocation("my_protobuf/bar/dir", ""), "E:\\Actual Path\\Directory"
            )
            self.assertEqual(
                r.Rlocation("my_protobuf/bar/dir/file", ""),
                "E:\\Actual Path\\Directory/file",
            )
            self.assertEqual(
                r.Rlocation("my_protobuf/bar/dir/de eply/nes ted/fi~le", ""),
                "E:\\Actual Path\\Directory/de eply/nes ted/fi~le",
            )

            self.assertIsNone(r.Rlocation("protobuf/foo/runfile"))
            self.assertIsNone(r.Rlocation("protobuf/bar/dir"))
            self.assertIsNone(r.Rlocation("protobuf/bar/dir/file"))
            self.assertIsNone(r.Rlocation("protobuf/bar/dir/dir/de eply/nes ted/fi~le"))

            self.assertEqual(
                r.Rlocation("_main/bar/runfile", ""),
                "/the/path/./to/other//other runfile.txt",
            )
            self.assertEqual(
                r.Rlocation("protobuf~3.19.2/foo/runfile", ""),
                "C:/Actual Path\\protobuf\\runfile",
            )
            self.assertEqual(
                r.Rlocation("protobuf~3.19.2/bar/dir", ""), "E:\\Actual Path\\Directory"
            )
            self.assertEqual(
                r.Rlocation("protobuf~3.19.2/bar/dir/file", ""),
                "E:\\Actual Path\\Directory/file",
            )
            self.assertEqual(
                r.Rlocation("protobuf~3.19.2/bar/dir/de eply/nes  ted/fi~le", ""),
                "E:\\Actual Path\\Directory/de eply/nes  ted/fi~le",
            )

            self.assertEqual(r.Rlocation("config.json", ""), "/etc/config.json")
            self.assertIsNone(r.Rlocation("_main", ""))
            self.assertIsNone(r.Rlocation("my_module", ""))
            self.assertIsNone(r.Rlocation("protobuf", ""))

    def testManifestBasedRlocationWithRepoMappingFromOtherRepo(self) -> None:
        with _MockFile(
            contents=[
                ",config.json,config.json~1.2.3",
                ",my_module,_main",
                ",my_protobuf,protobuf~3.19.2",
                ",my_workspace,_main",
                "protobuf~3.19.2,config.json,config.json~1.2.3",
                "protobuf~3.19.2,protobuf,protobuf~3.19.2",
            ]
        ) as rm, _MockFile(
            contents=[
                "_repo_mapping " + rm.Path(),
                "config.json /etc/config.json",
                "protobuf~3.19.2/foo/runfile C:/Actual Path\\protobuf\\runfile",
                "_main/bar/runfile /the/path/./to/other//other runfile.txt",
                "protobuf~3.19.2/bar/dir E:\\Actual Path\\Directory",
            ],
        ) as mf:
            r = runfiles.CreateManifestBased(mf.Path())

            self.assertEqual(
                r.Rlocation("protobuf/foo/runfile", "protobuf~3.19.2"),
                "C:/Actual Path\\protobuf\\runfile",
            )
            self.assertEqual(
                r.Rlocation("protobuf/bar/dir", "protobuf~3.19.2"),
                "E:\\Actual Path\\Directory",
            )
            self.assertEqual(
                r.Rlocation("protobuf/bar/dir/file", "protobuf~3.19.2"),
                "E:\\Actual Path\\Directory/file",
            )
            self.assertEqual(
                r.Rlocation(
                    "protobuf/bar/dir/de eply/nes  ted/fi~le", "protobuf~3.19.2"
                ),
                "E:\\Actual Path\\Directory/de eply/nes  ted/fi~le",
            )

            self.assertIsNone(r.Rlocation("my_module/bar/runfile", "protobuf~3.19.2"))
            self.assertIsNone(r.Rlocation("my_protobuf/foo/runfile", "protobuf~3.19.2"))
            self.assertIsNone(r.Rlocation("my_protobuf/bar/dir", "protobuf~3.19.2"))
            self.assertIsNone(
                r.Rlocation("my_protobuf/bar/dir/file", "protobuf~3.19.2")
            )
            self.assertIsNone(
                r.Rlocation(
                    "my_protobuf/bar/dir/de eply/nes  ted/fi~le", "protobuf~3.19.2"
                )
            )

            self.assertEqual(
                r.Rlocation("_main/bar/runfile", "protobuf~3.19.2"),
                "/the/path/./to/other//other runfile.txt",
            )
            self.assertEqual(
                r.Rlocation("protobuf~3.19.2/foo/runfile", "protobuf~3.19.2"),
                "C:/Actual Path\\protobuf\\runfile",
            )
            self.assertEqual(
                r.Rlocation("protobuf~3.19.2/bar/dir", "protobuf~3.19.2"),
                "E:\\Actual Path\\Directory",
            )
            self.assertEqual(
                r.Rlocation("protobuf~3.19.2/bar/dir/file", "protobuf~3.19.2"),
                "E:\\Actual Path\\Directory/file",
            )
            self.assertEqual(
                r.Rlocation(
                    "protobuf~3.19.2/bar/dir/de eply/nes  ted/fi~le", "protobuf~3.19.2"
                ),
                "E:\\Actual Path\\Directory/de eply/nes  ted/fi~le",
            )

            self.assertEqual(
                r.Rlocation("config.json", "protobuf~3.19.2"), "/etc/config.json"
            )
            self.assertIsNone(r.Rlocation("_main", "protobuf~3.19.2"))
            self.assertIsNone(r.Rlocation("my_module", "protobuf~3.19.2"))
            self.assertIsNone(r.Rlocation("protobuf", "protobuf~3.19.2"))

    def testDirectoryBasedRlocation(self) -> None:
        # The _DirectoryBased strategy simply joins the runfiles directory and the
        # runfile's path on a "/". This strategy does not perform any normalization,
        # nor does it check that the path exists.
        r = runfiles.CreateDirectoryBased("foo/bar baz//qux/")
        self.assertEqual(r.Rlocation("arg"), "foo/bar baz//qux/arg")
        if RunfilesTest.IsWindows():
            self.assertEqual(r.Rlocation("c:/foo"), "c:/foo")
            self.assertEqual(r.Rlocation("c:\\foo"), "c:\\foo")
        else:
            self.assertEqual(r.Rlocation("/foo"), "/foo")

    def testDirectoryBasedRlocationWithRepoMappingFromMain(self) -> None:
        with _MockFile(
            name="_repo_mapping",
            contents=[
                "_,config.json,config.json~1.2.3",
                ",my_module,_main",
                ",my_protobuf,protobuf~3.19.2",
                ",my_workspace,_main",
                "protobuf~3.19.2,config.json,config.json~1.2.3",
                "protobuf~3.19.2,protobuf,protobuf~3.19.2",
            ],
        ) as rm:
            dir = os.path.dirname(rm.Path())
            r = runfiles.CreateDirectoryBased(dir)

            self.assertEqual(
                r.Rlocation("my_module/bar/runfile", ""), dir + "/_main/bar/runfile"
            )
            self.assertEqual(
                r.Rlocation("my_workspace/bar/runfile", ""), dir + "/_main/bar/runfile"
            )
            self.assertEqual(
                r.Rlocation("my_protobuf/foo/runfile", ""),
                dir + "/protobuf~3.19.2/foo/runfile",
            )
            self.assertEqual(
                r.Rlocation("my_protobuf/bar/dir", ""), dir + "/protobuf~3.19.2/bar/dir"
            )
            self.assertEqual(
                r.Rlocation("my_protobuf/bar/dir/file", ""),
                dir + "/protobuf~3.19.2/bar/dir/file",
            )
            self.assertEqual(
                r.Rlocation("my_protobuf/bar/dir/de eply/nes ted/fi~le", ""),
                dir + "/protobuf~3.19.2/bar/dir/de eply/nes ted/fi~le",
            )

            self.assertEqual(
                r.Rlocation("protobuf/foo/runfile", ""), dir + "/protobuf/foo/runfile"
            )
            self.assertEqual(
                r.Rlocation("protobuf/bar/dir/dir/de eply/nes ted/fi~le", ""),
                dir + "/protobuf/bar/dir/dir/de eply/nes ted/fi~le",
            )

            self.assertEqual(
                r.Rlocation("_main/bar/runfile", ""), dir + "/_main/bar/runfile"
            )
            self.assertEqual(
                r.Rlocation("protobuf~3.19.2/foo/runfile", ""),
                dir + "/protobuf~3.19.2/foo/runfile",
            )
            self.assertEqual(
                r.Rlocation("protobuf~3.19.2/bar/dir", ""),
                dir + "/protobuf~3.19.2/bar/dir",
            )
            self.assertEqual(
                r.Rlocation("protobuf~3.19.2/bar/dir/file", ""),
                dir + "/protobuf~3.19.2/bar/dir/file",
            )
            self.assertEqual(
                r.Rlocation("protobuf~3.19.2/bar/dir/de eply/nes  ted/fi~le", ""),
                dir + "/protobuf~3.19.2/bar/dir/de eply/nes  ted/fi~le",
            )

            self.assertEqual(r.Rlocation("config.json", ""), dir + "/config.json")

    def testDirectoryBasedRlocationWithRepoMappingFromOtherRepo(self) -> None:
        with _MockFile(
            name="_repo_mapping",
            contents=[
                "_,config.json,config.json~1.2.3",
                ",my_module,_main",
                ",my_protobuf,protobuf~3.19.2",
                ",my_workspace,_main",
                "protobuf~3.19.2,config.json,config.json~1.2.3",
                "protobuf~3.19.2,protobuf,protobuf~3.19.2",
            ],
        ) as rm:
            dir = os.path.dirname(rm.Path())
            r = runfiles.CreateDirectoryBased(dir)

            self.assertEqual(
                r.Rlocation("protobuf/foo/runfile", "protobuf~3.19.2"),
                dir + "/protobuf~3.19.2/foo/runfile",
            )
            self.assertEqual(
                r.Rlocation("protobuf/bar/dir", "protobuf~3.19.2"),
                dir + "/protobuf~3.19.2/bar/dir",
            )
            self.assertEqual(
                r.Rlocation("protobuf/bar/dir/file", "protobuf~3.19.2"),
                dir + "/protobuf~3.19.2/bar/dir/file",
            )
            self.assertEqual(
                r.Rlocation(
                    "protobuf/bar/dir/de eply/nes  ted/fi~le", "protobuf~3.19.2"
                ),
                dir + "/protobuf~3.19.2/bar/dir/de eply/nes  ted/fi~le",
            )

            self.assertEqual(
                r.Rlocation("my_module/bar/runfile", "protobuf~3.19.2"),
                dir + "/my_module/bar/runfile",
            )
            self.assertEqual(
                r.Rlocation(
                    "my_protobuf/bar/dir/de eply/nes  ted/fi~le", "protobuf~3.19.2"
                ),
                dir + "/my_protobuf/bar/dir/de eply/nes  ted/fi~le",
            )

            self.assertEqual(
                r.Rlocation("_main/bar/runfile", "protobuf~3.19.2"),
                dir + "/_main/bar/runfile",
            )
            self.assertEqual(
                r.Rlocation("protobuf~3.19.2/foo/runfile", "protobuf~3.19.2"),
                dir + "/protobuf~3.19.2/foo/runfile",
            )
            self.assertEqual(
                r.Rlocation("protobuf~3.19.2/bar/dir", "protobuf~3.19.2"),
                dir + "/protobuf~3.19.2/bar/dir",
            )
            self.assertEqual(
                r.Rlocation("protobuf~3.19.2/bar/dir/file", "protobuf~3.19.2"),
                dir + "/protobuf~3.19.2/bar/dir/file",
            )
            self.assertEqual(
                r.Rlocation(
                    "protobuf~3.19.2/bar/dir/de eply/nes  ted/fi~le", "protobuf~3.19.2"
                ),
                dir + "/protobuf~3.19.2/bar/dir/de eply/nes  ted/fi~le",
            )

            self.assertEqual(
                r.Rlocation("config.json", "protobuf~3.19.2"), dir + "/config.json"
            )

    def testManifestBasedRlocationWithCompactRepoMappingPrefixes(self) -> None:
        """Test the new compact repo mapping format with prefixes."""
        with _MockFile(
            contents=[
                "+deps+*,aaa,target_aaa",
                "+deps+*,bbb,target_bbb", 
                "+deps+dep1,aaa,exact_target_aaa",  # Should take precedence over prefix
                "+other+*,ccc,target_ccc",
            ]
        ) as rm, _MockFile(
            contents=[
                "_repo_mapping " + rm.Path(),
                "target_aaa/file1 /path/to/target_aaa/file1",
                "exact_target_aaa/file2 /path/to/exact_target_aaa/file2",
                "target_bbb/file3 /path/to/target_bbb/file3",
                "target_ccc/file4 /path/to/target_ccc/file4",
            ],
        ) as mf:
            r = runfiles.CreateManifestBased(mf.Path())

            # Test prefixed mapping
            self.assertEqual(
                r.Rlocation("aaa/file1", "+deps+dep2"),
                "/path/to/target_aaa/file1",
            )
            self.assertEqual(
                r.Rlocation("bbb/file3", "+deps+dep3"),
                "/path/to/target_bbb/file3",
            )
            
            # Test exact mapping takes precedence over prefix
            self.assertEqual(
                r.Rlocation("aaa/file2", "+deps+dep1"),
                "/path/to/exact_target_aaa/file2",
            )
            
            # Test different prefix
            self.assertEqual(
                r.Rlocation("ccc/file4", "+other+some_repo"),
                "/path/to/target_ccc/file4",
            )
            
            # Test non-matching prefix - should return None since file doesn't exist in manifest
            self.assertIsNone(r.Rlocation("aaa/file1", "+different+repo"))

    def testManifestBasedRlocationWithCompactRepoMappingPrecedence(self) -> None:
        """Test that order matters for prefixed mappings (earlier prefix wins)."""
        with _MockFile(
            contents=[
                "+deps+*,shared,first_target",
                "+deps+dep*,shared,second_target",  # More specific but comes second
            ]
        ) as rm, _MockFile(
            contents=[
                "_repo_mapping " + rm.Path(),
                "first_target/file1 /path/to/first/file1",
                "second_target/file2 /path/to/second/file2",
            ],
        ) as mf:
            r = runfiles.CreateManifestBased(mf.Path())

            # Since "+deps+*" comes first, it should match "+deps+dep1" before "+deps+dep*"
            self.assertEqual(
                r.Rlocation("shared/file1", "+deps+dep1"),
                "/path/to/first/file1",
            )

    def testDirectoryBasedRlocationWithCompactRepoMappingPrefixes(self) -> None:
        """Test the new compact repo mapping format with prefixes for directory-based runfiles."""
        with _MockFile(
            name="_repo_mapping",
            contents=[
                "+deps+*,aaa,target_aaa",
                "+deps+*,bbb,target_bbb",
                "+deps+dep1,aaa,exact_target_aaa",  # Should take precedence over prefix
                "+other+*,ccc,target_ccc",
            ],
        ) as rm:
            dir = os.path.dirname(rm.Path())
            r = runfiles.CreateDirectoryBased(dir)

            # Test prefixed mapping
            self.assertEqual(
                r.Rlocation("aaa/file1", "+deps+dep2"),
                dir + "/target_aaa/file1",
            )
            self.assertEqual(
                r.Rlocation("bbb/file3", "+deps+dep3"),
                dir + "/target_bbb/file3",
            )
            
            # Test exact mapping takes precedence over prefix
            self.assertEqual(
                r.Rlocation("aaa/file2", "+deps+dep1"),
                dir + "/exact_target_aaa/file2",
            )
            
            # Test different prefix
            self.assertEqual(
                r.Rlocation("ccc/file4", "+other+some_repo"),
                dir + "/target_ccc/file4",
            )
            
            # Test non-matching prefix - directory-based returns path as-is when no mapping found
            self.assertEqual(
                r.Rlocation("aaa/file1", "+different+repo"),
                dir + "/aaa/file1",
            )

    def testCompactRepoMappingMixedExactAndPrefixed(self) -> None:
        """Test mixing old exact format with new prefixed format."""
        with _MockFile(
            contents=[
                ",old_style,old_target",  # Old exact format
                "+new+*,new_style,new_target",  # New prefixed format
                "+new+specific,new_style,specific_target",  # New exact format
            ]
        ) as rm, _MockFile(
            contents=[
                "_repo_mapping " + rm.Path(),
                "old_target/file1 /path/to/old/file1",
                "new_target/file2 /path/to/new/file2", 
                "specific_target/file3 /path/to/specific/file3",
            ],
        ) as mf:
            r = runfiles.CreateManifestBased(mf.Path())

            # Test old exact format still works
            self.assertEqual(
                r.Rlocation("old_style/file1", ""),
                "/path/to/old/file1",
            )
            
            # Test new prefixed format
            self.assertEqual(
                r.Rlocation("new_style/file2", "+new+repo1"),
                "/path/to/new/file2",
            )
            
            # Test exact takes precedence over prefix for new format
            self.assertEqual(
                r.Rlocation("new_style/file3", "+new+specific"),
                "/path/to/specific/file3",
            )

    def testCompactRepoMappingEdgeCases(self) -> None:
        """Test edge cases for compact repo mapping."""
        with _MockFile(
            contents=[
                "*,wildcard_target,wildcard_result",  # Prefix is just "*" (empty string prefix)
                "+,empty_plus,empty_plus_result",  # Prefix is just "+" 
                "+normal+*,normal,normal_result",
            ]
        ) as rm, _MockFile(
            contents=[
                "_repo_mapping " + rm.Path(),
                "wildcard_result/file1 /path/to/wildcard/file1",
                "empty_plus_result/file2 /path/to/empty_plus/file2",
                "normal_result/file3 /path/to/normal/file3",
            ],
        ) as mf:
            r = runfiles.CreateManifestBased(mf.Path())

            # Test wildcard prefix (empty string)
            self.assertEqual(
                r.Rlocation("wildcard_target/file1", "anything"),
                "/path/to/wildcard/file1",
            )
            
            # Test empty prefix after "+"
            self.assertEqual(
                r.Rlocation("empty_plus/file2", "+"),
                "/path/to/empty_plus/file2",
            )
            
            # Test normal prefix
            self.assertEqual(
                r.Rlocation("normal/file3", "+normal+repo"),
                "/path/to/normal/file3",
            )

    def testManifestBasedRlocationWithRepoMappingFromExtensionRepo(self) -> None:
        """Test repository mapping from extension repositories with prefixed entries.
        
        This test mirrors the Java test testManifestBasedRlocationWithRepoMapping_fromExtensionRepo
        to ensure compatibility with the compact repo mapping format.
        """
        with _MockFile(
            contents=[
                ",config.json,config.json~1.2.3",
                ",my_module,_main",
                ",my_protobuf,protobuf~3.19.2",
                ",my_workspace,_main",
                "my_module++ext+*,my_module,my_module+",
                "my_module++ext+*,repo1,my_module++ext+repo1",
            ]
        ) as rm, _MockFile(
            contents=[
                "_repo_mapping " + rm.Path(),
                "config.json /etc/config.json",
                "protobuf~3.19.2/foo/runfile C:/Actual Path\\protobuf\\runfile",
                "_main/bar/runfile /the/path/./to/other//other runfile.txt",
                "protobuf~3.19.2/bar/dir E:\\Actual Path\\Directory",
                "my_module+/foo/runfile /the/path/to/my_module+/runfile",
                "my_module++ext+repo1/foo/runfile /the/path/to/my_module++ext+repo1/runfile",
                "repo2+/foo/runfile /the/path/to/repo2+/runfile",
            ],
        ) as mf:
            r = runfiles.CreateManifestBased(mf.Path())

            # Test extension repository pattern: my_module++ext+* should match my_module++ext+repo1
            self.assertEqual(
                r.Rlocation("my_module/foo/runfile", "my_module++ext+repo1"),
                "/the/path/to/my_module+/runfile",
            )
            self.assertEqual(
                r.Rlocation("repo1/foo/runfile", "my_module++ext+repo1"),
                "/the/path/to/my_module++ext+repo1/runfile",
            )
            
            # Test that repository names with special characters work when no mapping is found
            self.assertEqual(
                r.Rlocation("repo2+/foo/runfile", "my_module++ext+repo1"),
                "/the/path/to/repo2+/runfile",
            )
            
            # Test from different extension repo that also matches the prefix
            self.assertEqual(
                r.Rlocation("my_module/foo/runfile", "my_module++ext+repo2"),
                "/the/path/to/my_module+/runfile",
            )
            self.assertEqual(
                r.Rlocation("repo1/foo/runfile", "my_module++ext+repo2"),
                "/the/path/to/my_module++ext+repo1/runfile",
            )

    def testDirectoryBasedRlocationWithRepoMappingFromExtensionRepo(self) -> None:
        """Test directory-based repository mapping from extension repositories with prefixed entries."""
        with _MockFile(
            name="_repo_mapping",
            contents=[
                ",config.json,config.json~1.2.3",
                ",my_module,_main",
                ",my_protobuf,protobuf~3.19.2",
                ",my_workspace,_main",
                "my_module++ext+*,my_module,my_module+",
                "my_module++ext+*,repo1,my_module++ext+repo1",
            ],
        ) as rm:
            dir = os.path.dirname(rm.Path())
            r = runfiles.CreateDirectoryBased(dir)

            # Test extension repository pattern
            self.assertEqual(
                r.Rlocation("my_module/foo", "my_module++ext+repo1"),
                dir + "/my_module+/foo",
            )
            self.assertEqual(
                r.Rlocation("repo1/foo", "my_module++ext+repo1"),
                dir + "/my_module++ext+repo1/foo",
            )
            self.assertEqual(
                r.Rlocation("repo2+/foo", "my_module++ext+repo1"),
                dir + "/repo2+/foo",
            )

    def testCurrentRepository(self) -> None:
        # Under bzlmod, the current repository name is the empty string instead
        # of the name in the workspace file.
        if bool(int(os.environ["BZLMOD_ENABLED"])):
            expected = ""
        else:
            expected = "rules_python"
        r = runfiles.Create({"RUNFILES_DIR": "whatever"})
        assert r is not None  # mypy doesn't understand the unittest api.
        self.assertEqual(r.CurrentRepository(), expected)

    @staticmethod
    def IsWindows() -> bool:
        return os.name == "nt"


class _MockFile:
    def __init__(
        self, name: Optional[str] = None, contents: Optional[List[Any]] = None
    ) -> None:
        self._contents = contents or []
        self._name = name or "x"
        self._path: Optional[str] = None

    def __enter__(self) -> Any:
        tmpdir = os.environ.get("TEST_TMPDIR")
        self._path = os.path.join(tempfile.mkdtemp(dir=tmpdir), self._name)
        with open(self._path, "wt", encoding="utf-8", newline="\n") as f:
            f.writelines(l + "\n" for l in self._contents)
        return self

    def __exit__(
        self,
        exc_type: Any,  # pylint: disable=unused-argument
        exc_value: Any,  # pylint: disable=unused-argument
        traceback: Any,  # pylint: disable=unused-argument
    ) -> None:
        if self._path:
            os.remove(self._path)
            os.rmdir(os.path.dirname(self._path))

    def Path(self) -> str:
        assert self._path is not None
        return self._path


if __name__ == "__main__":
    unittest.main()
